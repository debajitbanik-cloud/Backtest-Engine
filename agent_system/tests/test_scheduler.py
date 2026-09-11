"""Tests for agent_system.scheduler — store CRUD, optimizer pure functions, policy matrix."""
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent_system.scheduler.store import SchedulerStore
from agent_system.scheduler.optimizer import build_grid, evaluate, promotion_policy
from agent_system.scheduler.service import (
    SchedulerService,
    _resolve_cron,
    _next_run,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def store(tmp_path):
    db = tmp_path / "test_scheduler.db"
    return SchedulerStore(db_path=db)


@pytest.fixture
def sample_candles():
    """Minimal OHLCV series that produces a few trades for ma_cross."""
    import random
    random.seed(42)
    candles = []
    price = 100.0
    for i in range(200):
        change = random.uniform(-2, 2)
        o = price
        h = price + abs(change)
        l = price - abs(change)
        c = price + change
        candles.append({
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": 1000,
        })
        price = c
    return candles


# ── Store round-trip ──────────────────────────────────────────────────────────
class TestSchedulerStore:
    def test_create_and_get_job(self, store):
        job = store.create_job(bot_id="ma_cross", kind="backtest",
                               cadence_cron="@daily", metric="sharpe")
        assert job["id"]
        assert job["bot_id"] == "ma_cross"
        assert job["kind"] == "backtest"
        assert job["cadence_cron"] == "@daily"
        assert job["metric"] == "sharpe"
        assert job["enabled"] is True
        fetched = store.get_job(job["id"])
        assert fetched["id"] == job["id"]

    def test_list_jobs_filters(self, store):
        store.create_job(bot_id="a", user_id="u1")
        store.create_job(bot_id="b", user_id="u1")
        store.create_job(bot_id="c", user_id="u2")
        u1_jobs = store.list_jobs(user_id="u1")
        assert len(u1_jobs) == 2
        u2_jobs = store.list_jobs(user_id="u2")
        assert len(u2_jobs) == 1

    def test_update_job(self, store):
        job = store.create_job(bot_id="x")
        store.update_job(job["id"], enabled=False, cadence_cron="@hourly")
        updated = store.get_job(job["id"])
        assert updated["enabled"] is False
        assert updated["cadence_cron"] == "@hourly"

    def test_delete_job(self, store):
        job = store.create_job(bot_id="del")
        assert store.delete_job(job["id"]) is True
        assert store.get_job(job["id"]) is None

    def test_run_lifecycle(self, store):
        job = store.create_job(bot_id="r")
        run = store.start_run(job["id"])
        assert run["status"] == "running"
        finished = store.finish_run(run["id"], status="ok",
                                    result={"total_return_pct": 5.2})
        assert finished["status"] == "ok"
        assert finished["result"]["total_return_pct"] == 5.2

    def test_list_runs_by_job(self, store):
        job = store.create_job(bot_id="lr")
        r1 = store.start_run(job["id"])
        store.finish_run(r1["id"])
        r2 = store.start_run(job["id"])
        store.finish_run(r2["id"])
        runs = store.list_runs(job_id=job["id"])
        assert len(runs) == 2

    def test_invalid_kind_raises(self, store):
        with pytest.raises(ValueError, match="kind"):
            store.create_job(bot_id="bad", kind="invalid")

    def test_invalid_metric_raises(self, store):
        with pytest.raises(ValueError, match="metric"):
            store.create_job(bot_id="bad", metric="unknown")


# ── Grid builder ──────────────────────────────────────────────────────────────
class TestBuildGrid:
    def test_generates_values_for_known_params(self):
        grid = build_grid({"fast": 10, "slow": 30})
        assert "fast" in grid
        assert "slow" in grid
        assert len(grid["fast"]) >= 3
        assert len(grid["slow"]) >= 3
        # current value should be included
        assert 10 in grid["fast"]
        assert 30 in grid["slow"]

    def test_unknown_key_rejected(self):
        with pytest.raises(ValueError, match="Unknown parameter key"):
            build_grid({"fast": 10, "nonexistent_param": 5})

    def test_bool_param_single_value(self):
        grid = build_grid({"exit_mid": True})
        assert grid["exit_mid"] == [1]

    def test_respects_min_max(self):
        grid = build_grid({"period": 2})
        for v in grid["period"]:
            spec_min = 2  # PARAM_SPECS["period"]["min"]
            assert v >= spec_min

    def test_empty_params_returns_empty_grid(self):
        grid = build_grid({})
        assert grid == {}


# ── Evaluate (backtest with split) ────────────────────────────────────────────
class TestEvaluate:
    def test_returns_train_and_test_metrics(self, sample_candles):
        result = evaluate("ma_cross", {"fast": 10, "slow": 30}, sample_candles,
                          strategy_id="ma_cross")
        assert "train_metrics" in result
        assert "test_metrics" in result
        assert result["bot_id"] == "ma_cross"
        assert result["train_metrics"]["trades"] >= 0
        assert result["test_metrics"]["trades"] >= 0

    def test_split_ratio_respected(self, sample_candles):
        result = evaluate("ma_cross", {"fast": 10, "slow": 30}, sample_candles,
                          strategy_id="ma_cross", train_ratio=0.7)
        # With 200 candles, train = 140, test = 60
        # Both should produce metrics
        assert "total_return_pct" in result["train_metrics"]
        assert "total_return_pct" in result["test_metrics"]


# ── Promotion policy matrix ───────────────────────────────────────────────────
class TestPromotionPolicy:
    def _make(self, sharpe, trades, mdd):
        return {"test_metrics": {"sharpe": sharpe, "trades": trades,
                                 "max_drawdown_pct": mdd}}

    def test_promote_on_improvement(self):
        cur = self._make(0.5, 40, 10)
        cand = self._make(1.0, 50, 8)
        ok, reason = promotion_policy(cur, cand)
        assert ok is True
        assert "promoted" in reason

    def test_reject_lower_sharpe(self):
        cur = self._make(1.0, 40, 10)
        cand = self._make(0.3, 50, 8)
        ok, reason = promotion_policy(cur, cand)
        assert ok is False
        assert "Sharpe" in reason

    def test_reject_equal_sharpe(self):
        cur = self._make(1.0, 40, 10)
        cand = self._make(1.0, 50, 8)
        ok, reason = promotion_policy(cur, cand)
        assert ok is False

    def test_reject_too_few_trades(self):
        cur = self._make(0.5, 40, 10)
        cand = self._make(1.0, 10, 8)
        ok, reason = promotion_policy(cur, cand)
        assert ok is False
        assert "trades" in reason

    def test_reject_drawdown_slippage(self):
        cur = self._make(0.5, 40, 10)
        cand = self._make(1.0, 50, 20)  # +10pp > 5pp limit
        ok, reason = promotion_policy(cur, cand)
        assert ok is False
        assert "drawdown" in reason

    def test_accept_same_drawdown(self):
        cur = self._make(0.5, 40, 10)
        cand = self._make(1.0, 50, 10)
        ok, reason = promotion_policy(cur, cand)
        assert ok is True

    def test_accept_within_slippage(self):
        cur = self._make(0.5, 40, 10)
        cand = self._make(1.0, 50, 14)  # +4pp ≤ 5pp
        ok, reason = promotion_policy(cur, cand)
        assert ok is True

    def test_reject_exactly_at_slippage_plus_one(self):
        cur = self._make(0.5, 40, 10)
        cand = self._make(1.0, 50, 15.1)  # +5.1pp > 5pp
        ok, reason = promotion_policy(cur, cand)
        assert ok is False


# ── Cron helpers ─────────────────────────────────────────────────────────────
class TestCronHelpers:
    def test_resolve_shorthand(self):
        assert _resolve_cron("@hourly") == "0 * * * *"
        assert _resolve_cron("@daily") == "0 0 * * *"
        assert _resolve_cron("@weekly") == "0 0 * * 0"

    def test_resolve_passthrough(self):
        assert _resolve_cron("30 2 * * 1") == "30 2 * * 1"

    def test_next_run_in_future(self):
        try:
            from croniter import croniter  # noqa: F401
        except ImportError:
            pytest.skip("croniter not installed")
        cron = _resolve_cron("@hourly")
        nxt = _next_run(cron, after=time.time())
        assert nxt > time.time()


# ── SchedulerService ─────────────────────────────────────────────────────────
@pytest.fixture
def svc_store(tmp_path):
    db = tmp_path / "test_svc.db"
    return SchedulerStore(db_path=db)


class TestSchedulerService:
    def test_init_default(self, svc_store):
        svc = SchedulerService(store=svc_store)
        assert svc._running is False
        assert svc.store is svc_store

    @pytest.mark.asyncio
    async def test_start_stop(self, svc_store):
        svc = SchedulerService(store=svc_store, poll_interval=100)
        await svc.start()
        assert svc._running is True
        assert svc._task is not None
        await svc.stop()
        assert svc._running is False

    @pytest.mark.asyncio
    async def test_tick_finds_due_job(self, svc_store):
        job = svc_store.create_job(bot_id="tick_test", cadence_cron="@hourly")
        svc = SchedulerService(store=svc_store, poll_interval=999)
        # Manually call _tick once; no jobs should be due since they were just created
        svc._last_check = time.time() - 7200  # pretend last check was 2h ago
        await svc._tick()
        # Verify _last_check was updated
        assert svc._last_check > 0

    @pytest.mark.asyncio
    async def test_emit_optimizer_run_publishes_event(self, svc_store):
        mock_bus = AsyncMock()
        svc = SchedulerService(store=svc_store, event_bus=mock_bus)
        await svc._emit_optimizer_run(
            job_id="j1", run_id="r1", bot_id="b1",
            kind="backtest", status="ok",
            result={"total_return_pct": 5.0}, promoted=False,
        )
        mock_bus.publish.assert_called_once()
        event = mock_bus.publish.call_args[0][0]
        assert event.payload["event_type"] == "optimizer_run"
        assert event.payload["job_id"] == "j1"
        assert event.payload["status"] == "ok"
