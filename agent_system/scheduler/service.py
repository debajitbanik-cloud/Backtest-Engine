"""Scheduler Service — background loop that ticks every 30 s, checks cron
schedules, runs backtests/optimization in a thread, records runs, and emits
SSE events via the event bus.

Heavy compute (backtest, optimize) is dispatched via asyncio.to_thread so the
event loop stays responsive.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional

from agent_system.scheduler.store import SchedulerStore

logger = logging.getLogger(__name__)

# ── Cron helpers ────────────────────────────────────────────────────────────

_SHORTHAND = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
}


def _resolve_cron(expr: str) -> str:
    """Resolve ``@shorthand`` to standard 5-field cron, or return as-is."""
    return _SHORTHAND.get(expr.strip(), expr.strip())


def _next_run(cron_expr: str, after: Optional[float] = None) -> float:
    """Return the next epoch timestamp after *after* for *cron_expr*."""
    from croniter import croniter

    dt = datetime.fromtimestamp(after or time.time())
    return croniter(cron_expr, dt).get_next(float)


# ── Service ─────────────────────────────────────────────────────────────────


class SchedulerService:
    """Background service that runs scheduled backtest / optimize jobs.

    Parameters
    ----------
    store : SchedulerStore
        Backing store for jobs and runs.
    event_bus : EventBus
        System event bus (used to emit SSE events on run completion).
    poll_interval : float
        Seconds between loop iterations (default 30).
    """

    def __init__(
        self,
        store: Optional[SchedulerStore] = None,
        event_bus: Any = None,
        poll_interval: float = 30.0,
    ):
        self.store = store or SchedulerStore()
        self._event_bus = event_bus
        self._poll_interval = poll_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_check: float = 0.0

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background tick loop (non-blocking)."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self.run())
        logger.info("SchedulerService started (poll=%ss)", self._poll_interval)

    async def stop(self) -> None:
        """Gracefully cancel the background task."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SchedulerService stopped")

    async def run(self) -> None:
        """Run the service loop (blocking — used as an asyncio.create_task target)."""
        self._running = True
        try:
            while self._running:
                await self._tick()
                await asyncio.sleep(self._poll_interval)
        except asyncio.CancelledError:
            logger.info("SchedulerService loop cancelled")
        finally:
            self._running = False

    # ── Core loop ────────────────────────────────────────────────────────────

    async def _tick(self) -> None:
        """One iteration: find due jobs and execute them."""
        now = time.time()
        try:
            jobs = self.store.list_jobs(enabled_only=True)
        except Exception as exc:
            logger.error("Failed to list scheduler jobs: %s", exc)
            return

        for job in jobs:
            try:
                cron_raw = job.get("cadence_cron", "@weekly")
                cron_expr = _resolve_cron(cron_raw)
                nxt = _next_run(cron_expr, after=self._last_check)
                if nxt <= now:
                    asyncio.create_task(self._run_job(job))
            except Exception as exc:
                logger.error("Error scheduling job %s: %s", job.get("id"), exc)

        self._last_check = now

    # ── Job execution ────────────────────────────────────────────────────────

    async def _run_job(self, job: Dict[str, Any]) -> None:
        """Execute a single job: create run → compute → finish → emit event."""
        job_id = job["id"]
        user_id = job.get("user_id", "default")
        bot_id = job["bot_id"]
        kind = job.get("kind", "backtest")
        metric = job.get("metric", "sharpe")
        grid = job.get("grid", {})

        run = self.store.start_run(job_id, user_id=user_id)
        run_id = run["id"]

        try:
            # Fetch candles via delta_client (heavy I/O — to_thread)
            candles = await asyncio.to_thread(self._fetch_candles, bot_id)

            # Heavy compute in a thread
            if kind == "optimize":
                result = await asyncio.to_thread(
                    self._run_optimize, bot_id, grid, candles, metric
                )
            else:
                params = self._get_current_params(bot_id)
                result = await asyncio.to_thread(
                    self._run_backtest, bot_id, params, candles
                )

            # Promotion policy
            promoted = False
            if kind == "optimize" and result:
                current = self._get_current_result(bot_id)
                if current:
                    from agent_system.scheduler.optimizer import promotion_policy
                    promoted, _reason = promotion_policy(current, result)

            self.store.finish_run(
                run_id,
                status="ok",
                result=result,
                promoted=promoted,
            )

            # Emit SSE event via event bus
            await self._emit_optimizer_run(
                job_id=job_id,
                run_id=run_id,
                bot_id=bot_id,
                kind=kind,
                status="ok",
                result=result,
                promoted=promoted,
            )

        except Exception as exc:
            logger.error("Job %s run %s failed: %s", job_id, run_id, exc)
            self.store.finish_run(run_id, status="error", result={"error": str(exc)})
            await self._emit_optimizer_run(
                job_id=job_id,
                run_id=run_id,
                bot_id=bot_id,
                kind=kind,
                status="error",
                result={"error": str(exc)},
                promoted=False,
            )

    # ── Data helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _fetch_candles(bot_id: str, symbol: str = "BTCUSD",
                       timeframe: str = "1h", limit: int = 500) -> list:
        """Fetch OHLCV candles from Delta. Runs in a thread."""
        import sys as _sys
        from pathlib import Path
        agent_root = str(Path(__file__).parent.parent)
        if agent_root not in _sys.path:
            _sys.path.insert(0, agent_root)

        from data.delta_api_client import delta_client

        try:
            import socket as _sock
            import aiohttp as _aiohttp
            from urllib.parse import urlencode as _urlencode

            tf_sec = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
            import time as _time
            now = int(_time.time())
            params = {
                "symbol": symbol,
                "resolution": timeframe,
                "limit": str(limit),
                "start": str(now - (tf_sec.get(timeframe, 3600) * limit)),
                "end": str(now),
            }
            url = f"{delta_client.rest_base}/v2/history/candles?{_urlencode(params)}"
            import urllib.request
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = json.loads(resp.read())
            raw = data.get("result", []) if isinstance(data, dict) else []
            return [
                {
                    "open": float(c.get("open", c.get("Open", 0))),
                    "high": float(c.get("high", c.get("High", 0))),
                    "low": float(c.get("low", c.get("Low", 0))),
                    "close": float(c.get("close", c.get("Close", 0))),
                    "volume": float(c.get("volume", c.get("Volume", 0))),
                }
                for c in raw
                if float(c.get("close", c.get("Close", 0))) > 0
            ]
        except Exception as exc:
            logger.warning("Candle fetch failed for %s: %s", bot_id, exc)
            return []

    @staticmethod
    def _run_backtest(bot_id: str, params: Dict[str, Any], candles: list) -> Dict[str, Any]:
        """Run a backtest evaluation. Runs in a thread."""
        import sys as _sys
        from pathlib import Path
        agent_root = str(Path(__file__).parent.parent)
        if agent_root not in _sys.path:
            _sys.path.insert(0, agent_root)

        from agent_system.scheduler.optimizer import evaluate

        return evaluate(bot_id, params, candles)

    @staticmethod
    def _run_optimize(bot_id: str, grid: Dict[str, Any], candles: list,
                      metric: str = "sharpe") -> Dict[str, Any]:
        """Run grid-search optimization. Runs in a thread."""
        import sys as _sys
        from pathlib import Path
        agent_root = str(Path(__file__).parent.parent)
        if agent_root not in _sys.path:
            _sys.path.insert(0, agent_root)

        from agent_system.core.strategy_library import run_backtest
        import itertools

        if not grid:
            return {"error": "empty grid"}

        param_keys = list(grid.keys())
        param_values = list(grid.values())
        best = None
        best_score = float("-inf")
        total = 1
        for v in param_values:
            total *= len(v)

        for combo in itertools.product(*param_values):
            params = dict(zip(param_keys, combo))
            try:
                metrics = run_backtest(bot_id, candles, params)
                score = metrics.get(metric, 0)
                if score > best_score:
                    best_score = score
                    best = {"params": params, "metrics": metrics}
            except Exception:
                continue

        return best or {"params": {}, "metrics": {}}

    @staticmethod
    def _get_current_params(bot_id: str) -> Dict[str, Any]:
        """Get the latest bot_backtest params from trade_journal.db."""
        import sys as _sys
        from pathlib import Path
        agent_root = str(Path(__file__).parent.parent)
        if agent_root not in _sys.path:
            _sys.path.insert(0, agent_root)

        from agent_system.core.trade_journal import trade_journal

        rows = trade_journal.get_bot_backtests(bot_id, limit=1)
        if rows:
            return rows[0].get("params", {})
        return {}

    @staticmethod
    def _get_current_result(bot_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest bot_backtest result for promotion comparison."""
        import sys as _sys
        from pathlib import Path
        agent_root = str(Path(__file__).parent.parent)
        if agent_root not in _sys.path:
            _sys.path.insert(0, agent_root)

        from agent_system.core.trade_journal import trade_journal

        rows = trade_journal.get_bot_backtests(bot_id, limit=1)
        if rows:
            return {"test_metrics": rows[0].get("metrics", {}), "params": rows[0].get("params", {})}
        return None

    # ── Event emission ───────────────────────────────────────────────────────

    async def _emit_optimizer_run(
        self,
        job_id: str,
        run_id: str,
        bot_id: str,
        kind: str,
        status: str,
        result: Dict[str, Any],
        promoted: bool,
    ) -> None:
        """Publish an optimizer_run event to the SSE stream."""
        if not self._event_bus:
            return
        try:
            import sys as _sys
            from pathlib import Path
            agent_root = str(Path(__file__).parent.parent)
            if agent_root not in _sys.path:
                _sys.path.insert(0, agent_root)

            from core.event_bus import Event, EventType

            await self._event_bus.publish(
                Event(
                    type=EventType.OPTIMIZATION_UPDATE,
                    payload={
                        "event_type": "optimizer_run",
                        "job_id": job_id,
                        "run_id": run_id,
                        "bot_id": bot_id,
                        "kind": kind,
                        "status": status,
                        "result": result,
                        "promoted": promoted,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                    source_agent="SchedulerService",
                )
            )
        except Exception as exc:
            logger.error("Failed to emit optimizer_run event: %s", exc)
