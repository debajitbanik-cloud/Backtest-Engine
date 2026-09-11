"""Optimizer — pure functions for parameter grid building, backtest evaluation,
and promotion policy. No I/O; all side effects go through store.py.

Depends on agent_system.core.strategy_library for run_backtest().
bot_backtests lives in trade_journal.db (Task 3); this module only reads from
that table when needed, never writes to it.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from agent_system.core.strategy_library import (
    PARAM_SPECS,
    run_backtest,
    get_strategy,
)

# Promotion thresholds (from spec §promotion_policy)
_MIN_TRADES = 30
_MAX_DD_SLIPPAGE_PP = 5.0  # allowed increase in max_drawdown (percentage points)


def build_grid(bot_params: Dict[str, Any]) -> Dict[str, List[float]]:
    """Build an optimisation grid from a bot's declared params.

    For each numeric param, generates values at current ±2 steps (step size
    derived from PARAM_SPECS). Non-numeric or boolean params are kept as-is
    (single-element list). Unknown keys (not in bot_params) are rejected —
    caller must not supply keys the bot doesn't declare.

    Raises ValueError if any key is not present in bot_params.
    """
    grid: Dict[str, List[float]] = {}
    for key, value in bot_params.items():
        spec = PARAM_SPECS.get(key)
        if spec is None:
            raise ValueError(f"Unknown parameter key: {key!r}")
        if spec.get("type") == "bool":
            grid[key] = [int(bool(value))]
            continue
        lo = spec.get("min")
        hi = spec.get("max")
        if lo is None or hi is None:
            grid[key] = [float(value)]
            continue
        # Step = (max - min) / 10, clamped to at least 1 for ints
        span = hi - lo
        raw_step = span / 10.0
        if spec.get("type") == "int":
            step = max(1.0, round(raw_step))
        else:
            step = max(raw_step, span / 100.0)  # at least 1% of range
        vals = set()
        for offset in (-2, -1, 0, 1, 2):
            v = value + offset * step
            v = max(lo, min(hi, v))
            if spec.get("type") == "int":
                v = int(round(v))
            else:
                v = round(v, 4)
            vals.add(v)
        grid[key] = sorted(vals)
    return grid


def evaluate(bot_id: str, params: Dict[str, Any], candles: List[Dict[str, Any]],
             strategy_id: Optional[str] = None,
             train_ratio: float = 0.7) -> Dict[str, Any]:
    """Run a backtest with a 70/30 train/test split.

    Returns:
        {
          "train_metrics": {...},
          "test_metrics": {...},
          "params": {...},
          "bot_id": str,
        }

    If candles are too short for a meaningful split, the full set is used for
    both train and test.
    """
    n = len(candles)
    split_idx = max(1, int(n * train_ratio))
    train_candles = candles[:split_idx]
    test_candles = candles[split_idx:]

    sid = strategy_id or bot_id
    train_metrics = run_backtest(sid, train_candles, params)
    # If test set is too small, fall back to full-set metrics
    if len(test_candles) < 10:
        test_metrics = run_backtest(sid, candles, params)
    else:
        test_metrics = run_backtest(sid, test_candles, params)

    return {
        "bot_id": bot_id,
        "params": params,
        "train_metrics": train_metrics,
        "test_metrics": test_metrics,
    }


# Type alias for clarity
Optional = __import__("typing").Optional


def promotion_policy(current: Dict[str, Any], candidate: Dict[str, Any]) -> Tuple[bool, str]:
    """Decide whether `candidate` should replace `current` parameters.

    Args:
        current:  {"train_metrics": {...}, "test_metrics": {...}, "params": {...}}
        candidate: same shape.

    Returns:
        (promote: bool, reason: str)

    Promotion criteria (all must hold):
      1. OOS (test) Sharpe of candidate > OOS Sharpe of current
      2. Candidate test trades ≥ _MIN_TRADES
      3. Candidate test max_drawdown ≤ current test max_drawdown + _MAX_DD_SLIPPAGE_PP
    """
    cur_test = current.get("test_metrics", {})
    cand_test = candidate.get("test_metrics", {})

    cur_sharpe = cur_test.get("sharpe", 0)
    cand_sharpe = cand_test.get("sharpe", 0)
    cand_trades = cand_test.get("trades", 0)
    cand_mdd = cand_test.get("max_drawdown_pct", 0)
    cur_mdd = cur_test.get("max_drawdown_pct", 0)

    if cand_trades < _MIN_TRADES:
        return False, f"candidate trades {cand_trades} < {_MIN_TRADES} minimum"

    if cand_mdd > cur_mdd + _MAX_DD_SLIPPAGE_PP:
        return (False,
                f"candidate drawdown {cand_mdd:.1f}% exceeds current {cur_mdd:.1f}% "
                f"by >{_MAX_DD_SLIPPAGE_PP}pp")

    if cand_sharpe <= cur_sharpe:
        return (False,
                f"candidate OOS Sharpe {cand_sharpe:.2f} ≤ current {cur_sharpe:.2f}")

    return True, f"promoted: OOS Sharpe {cur_sharpe:.2f} → {cand_sharpe:.2f}, trades={cand_trades}"
