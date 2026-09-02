"""
Agent M Candle-Signal Strategy Integration
===========================================
Wraps the candle-signal backtest from the agentic-ai-trading-be repo
(trading-agent-m/app/backtest/backtest.py) so it can be run on demand by the
Python bridge and return JSON metrics for the UI.

The strategy: daily OHLCV candle type (bullish → BUY, bearish → SELL) filtered
by SMA50/200 trend, with conservative / aggressive risk profiling applied via
the repo's risk_evaluation_metrics() and a forward TP/SL walk (max hold days).

This module reuses the repo's pure functions (compute_indicators, row_to_yahoo,
candle_to_action, _derive_confidence, simulate_outcome, risk_evaluation_metrics)
but reimplements the run loop to return structured JSON instead of printing,
so the UI/bridge can consume it.
"""
from __future__ import annotations

import json
import os
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# The cloned repo lives at the project root. Config requires a (dummy) API key.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent / "agentic-ai-trading-be"
AGENTM_DIR = REPO_ROOT / "trading-agent-m"
os.environ.setdefault("PERPLEXITY_API_KEY", "dummy")

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_FILE = RESULTS_DIR / "agentm_candle_results.json"

MAX_HOLD_DAYS = 10
PROFILES = ("conservative", "aggressive")


def _import_repo():
    """Import the repo's backtest/risk modules without triggering package __init__
    files (which pull in fastapi, langgraph, etc.). Registers synthetic packages
    that expose the real submodule files on sys.path."""
    base = str(AGENTM_DIR)
    if base not in sys.path:
        sys.path.insert(0, base)

    for name, sub in (
        ("app", "app"),
        ("app.agents", "app/agents"),
        ("app.agents.nodes", "app/agents/nodes"),
        ("app.core", "app/core"),
        ("app.backtest", "app/backtest"),
    ):
        if name not in sys.modules:
            pkg = types.ModuleType(name)
            pkg.__path__ = [str(AGENTM_DIR / sub)]
            pkg.__spec__ = None
            sys.modules[name] = pkg

    from app.agents.nodes.risk_adjust import (
        PROFILE_PARAMS,
        risk_evaluation_metrics,
    )
    from app.agents.state import (
        RiskProfile,
        TradeAction,
        TradingDecision,
    )
    from app.backtest.backtest import (
        _derive_confidence,
        candle_to_action,
        compute_indicators,
        row_to_yahoo,
        simulate_outcome,
    )

    return {
        "PROFILE_PARAMS": PROFILE_PARAMS,
        "risk_evaluation_metrics": risk_evaluation_metrics,
        "RiskProfile": RiskProfile,
        "TradeAction": TradeAction,
        "TradingDecision": TradingDecision,
        "_derive_confidence": _derive_confidence,
        "candle_to_action": candle_to_action,
        "compute_indicators": compute_indicators,
        "row_to_yahoo": row_to_yahoo,
        "simulate_outcome": simulate_outcome,
    }


_MOD = None


def repo_available() -> bool:
    """Check whether the agentic-ai-trading-be repo is present."""
    return (AGENTM_DIR / "app" / "backtest" / "backtest.py").exists()


def get_repo() -> dict:
    """Memoized repo function bundle."""
    global _MOD
    if _MOD is None:
        _MOD = _import_repo()
    return _MOD


def run_backtest(
    ticker: str = "AAPL",
    start: str = "2024-01-01",
    end: str = "2025-01-01",
    account_bp: float = 10000.0,
    profiles: Optional[List[str]] = None,
    limit_days: int = 0,
) -> Dict[str, Any]:
    """Run the Agent M candle-signal backtest with risk profiling.

    Args:
        ticker: Yahoo Finance symbol.
        start/end: ISO date range.
        account_bp: Simulated buying power.
        profiles: Which risk profiles to run (subset of conservative/aggressive).
        limit_days: If > 0, truncate the prepared dataframe (quick smoke test).

    Returns:
        A JSON-serializable dict of results.
    """
    if not repo_available():
        raise FileNotFoundError(f"Agent M repo not found. Expected: {AGENTM_DIR}")

    import numpy as np
    import pandas as pd
    import yfinance as yf

    mod = get_repo()
    risk_evaluation_metrics = mod["risk_evaluation_metrics"]
    RiskProfile = mod["RiskProfile"]
    TradeAction = mod["TradeAction"]
    TradingDecision = mod["TradingDecision"]
    compute_indicators = mod["compute_indicators"]
    row_to_yahoo = mod["row_to_yahoo"]
    candle_to_action = mod["candle_to_action"]
    _derive_confidence = mod["_derive_confidence"]
    simulate_outcome = mod["simulate_outcome"]

    if not profiles:
        profiles = list(PROFILES)

    started = time.time()
    raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if raw.empty:
        raise ValueError(f"No data returned for {ticker}")

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw.columns = [c.title() for c in raw.columns]

    df = compute_indicators(raw).dropna(subset=["sma50", "atr14", "rsi"])
    if limit_days > 0:
        df = df.iloc[:limit_days]
    if df.empty:
        raise ValueError(f"Not enough data for {ticker} in range")

    period = f"{df.index[0].date()} - {df.index[-1].date()} ({len(df)} trading days)"
    all_trades: Dict[str, List[Dict[str, Any]]] = {p: [] for p in profiles}

    for i, (date, row) in enumerate(df.iterrows()):
        yahoo = row_to_yahoo(row, period_summary=period)
        action = candle_to_action(yahoo.candle_type, yahoo.sma50, yahoo.sma200)
        if action is None:
            continue

        confidence = _derive_confidence(yahoo, action)
        entry = float(row["Close"])
        sl_placeholder = entry * (0.97 if action == TradeAction.BUY else 1.03)
        tp_placeholder = entry * (1.06 if action == TradeAction.BUY else 0.94)

        trade = TradingDecision(
            action=action,
            confidence=confidence,
            entry_price=entry,
            stop_loss=sl_placeholder,
            take_profit=tp_placeholder,
            qty=1.0,
            risk_reward="2:1",
            thesis=f"Candle signal: {yahoo.candle_type}",
            current_stock_price=entry,
            ticker=ticker,
        )

        for profile in profiles:
            assessment = risk_evaluation_metrics(trade, yahoo, account_bp, RiskProfile(profile))
            adj = assessment.adjusted_trade

            if assessment.risk_status in ("BLOCKED", "REVIEW") or adj.qty == 0:
                all_trades[profile].append({
                    "date": date.strftime("%Y-%m-%d"),
                    "action": action.value,
                    "candle": yahoo.candle_type,
                    "outcome": assessment.risk_status,
                    "pnl": 0.0,
                    "days": 0,
                    "rr": 0.0,
                    "score": assessment.risk_score,
                    "qty": 0,
                })
                continue

            outcome, exit_price, days = simulate_outcome(
                df, i, adj.take_profit, adj.stop_loss, action
            )

            pnl = (
                (exit_price - adj.entry_price) * adj.qty if action == TradeAction.BUY
                else (adj.entry_price - exit_price) * adj.qty
            )

            try:
                rr = float(assessment.metrics.actual_rr.split(":")[0])
            except (ValueError, AttributeError):
                rr = 0.0

            all_trades[profile].append({
                "date": date.strftime("%Y-%m-%d"),
                "action": action.value,
                "candle": yahoo.candle_type,
                "outcome": outcome,
                "pnl": round(pnl, 2),
                "days": days,
                "rr": round(rr, 2),
                "score": round(assessment.risk_score, 3),
                "entry": round(adj.entry_price, 2),
                "tp": round(adj.take_profit, 2),
                "sl": round(adj.stop_loss, 2),
                "qty": adj.qty,
            })

    elapsed = time.time() - started

    profile_results = {}
    for profile in profiles:
        trades = all_trades[profile]
        active = [t for t in trades if t["outcome"] not in ("BLOCKED", "REVIEW")]
        blocked = len([t for t in trades if t["outcome"] == "BLOCKED"])
        reviewed = len([t for t in trades if t["outcome"] == "REVIEW"])
        wins = [t for t in active if t["outcome"] == "TP"]
        losses = [t for t in active if t["outcome"] == "SL"]
        expired = [t for t in active if t["outcome"] == "EXPIRED"]

        total_pnl = sum(t["pnl"] for t in active)
        win_rate = len(wins) / len(active) * 100 if active else 0.0
        avg_days = sum(t["days"] for t in active) / len(active) if active else 0.0
        avg_rr = sum(t["rr"] for t in active) / len(active) if active else 0.0
        avg_score = sum(t["score"] for t in active) / len(active) if active else 0.0

        gross_profit = sum(t["pnl"] for t in active if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in active if t["pnl"] < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (
            float("inf") if gross_profit > 0 else 0.0
        )

        candle_stats = {}
        for t in active:
            ct = t["candle"]
            candle_stats.setdefault(ct, {"total": 0, "wins": 0, "pnl": 0.0})
            candle_stats[ct]["total"] += 1
            if t["outcome"] == "TP":
                candle_stats[ct]["wins"] += 1
            candle_stats[ct]["pnl"] += t["pnl"]

        profile_results[profile] = {
            "signals": len(trades),
            "blocked": blocked,
            "reviewed": reviewed,
            "executed": len(active),
            "wins": len(wins),
            "losses": len(losses),
            "expired": len(expired),
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else None,
            "avg_hold_days": round(avg_days, 2),
            "avg_rr": round(avg_rr, 2),
            "avg_risk_score": round(avg_score, 3),
            "candle_stats": {
                ct: {
                    "total": s["total"],
                    "win_rate": round(s["wins"] / s["total"] * 100, 1) if s["total"] else 0.0,
                    "pnl": round(s["pnl"], 2),
                }
                for ct, s in sorted(candle_stats.items(), key=lambda x: -x[1]["pnl"])
            },
            "trades": trades,
        }

    return {
        "strategy_name": "Agent M Candle-Signal (Risk Profiled)",
        "symbol": ticker,
        "timeframe": "1d",
        "framework": "agentm",
        "status": "success",
        "period": period,
        "metrics": {p: {k: v for k, v in profile_results[p].items() if k != "trades"} for p in profiles},
        "profiles": profile_results,
        "config": {
            "account_bp": account_bp,
            "max_hold_days": MAX_HOLD_DAYS,
            "limit_days": limit_days,
        },
        "elapsed_seconds": round(elapsed, 2),
        "updated": datetime.now(timezone.utc).isoformat(),
    }


def save_results(result: Dict[str, Any]) -> Path:
    """Persist results to the results directory."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_FILE.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return RESULTS_FILE


def load_cached_results() -> Optional[Dict[str, Any]]:
    """Load previously saved backtest results, if any."""
    if not RESULTS_FILE.exists():
        return None
    try:
        return json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_status() -> Dict[str, Any]:
    """Return integration status + cached results for the UI."""
    cached = load_cached_results()
    return {
        "available": repo_available(),
        "repo_dir": str(AGENTM_DIR),
        "has_cached_results": cached is not None,
        "results": cached,
    }


if __name__ == "__main__":
    # CLI smoke test
    import json as _json

    r = run_backtest(limit_days=60, account_bp=10000.0)
    print(_json.dumps(r["metrics"], indent=2))