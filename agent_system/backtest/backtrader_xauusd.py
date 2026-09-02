"""
Backtrader XAUUSD Pullback Strategy Integration
=================================================
Wraps the SunriseOgle strategy from the backtrader-pullback-window-xauusd repo
so it can be run on demand by the Python bridge and return JSON metrics for the UI.

Runs a backtest with configurable parameters and returns:
  - performance metrics (return, sharpe, max drawdown, win rate, profit factor)
  - trade statistics
  - the parameter overrides that were used
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# The cloned strategy repo lives at the project root.
REPO_DIR = Path(__file__).resolve().parent.parent.parent / "backtrader-pullback-window-xauusd"
STRATEGY_FILE = REPO_DIR / "src" / "strategy" / "sunrise_ogle_xauusd.py"
DATA_FILE = REPO_DIR / "data" / "XAUUSD_5m_5Yea.csv"

# Results are cached here so the UI can poll without re-running.
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_FILE = RESULTS_DIR / "backtrader_xauusd_results.json"

# Whitelist of strategy params we allow the UI / bridge to override.
TUNEABLE_PARAMS: Dict[str, Any] = {
    "ema_fast_length": 14,
    "ema_medium_length": 14,
    "ema_slow_length": 24,
    "ema_confirm_length": 1,
    "ema_filter_price_length": 100,
    "atr_length": 10,
    "long_atr_sl_multiplier": 4.5,
    "long_atr_tp_multiplier": 6.5,
    "short_atr_sl_multiplier": 2.5,
    "short_atr_tp_multiplier": 6.5,
    "long_use_pullback_entry": True,
    "long_pullback_max_candles": 3,
    "long_entry_window_periods": 1,
    "short_use_pullback_entry": True,
    "short_pullback_max_candles": 2,
    "short_entry_window_periods": 7,
    "enable_long_trades": True,
    "enable_short_trades": False,
    "risk_percent": 0.01,
    "window_offset_multiplier": 1.0,
    "use_window_time_offset": False,
    "window_price_offset_multiplier": 0.001,
}


def strategy_available() -> bool:
    """Check whether the strategy repo and data file are present."""
    return STRATEGY_FILE.exists() and DATA_FILE.exists()


def load_strategy_module():
    """Import the SunriseOgle module in a backtrader-safe way."""
    if not strategy_available():
        raise FileNotFoundError(
            f"Strategy repo not found. Expected: {STRATEGY_FILE} and {DATA_FILE}"
        )
    mod_name = "sunrise_ogle"
    spec = importlib.util.spec_from_file_location(mod_name, str(STRATEGY_FILE))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    # Disable noisy console / file output for programmatic runs.
    mod.EXPORT_TRADE_REPORTS = False
    mod.TRADE_REPORT_ENABLED = False
    mod.ENABLE_PLOT = False
    mod.VERBOSE_DEBUG = False
    return mod


def _load_module() -> "module":
    """Memoized strategy module import."""
    return load_strategy_module()


def run_backtest(
    params: Optional[Dict[str, Any]] = None,
    starting_cash: float = 100000.0,
    limit_bars: int = 0,
    quiet: bool = True,
) -> Dict[str, Any]:
    """Run the SunriseOgle backtrader strategy on XAUUSD 5m data.

    Args:
        params: Optional overrides for the whitelisted strategy params.
        starting_cash: Initial account balance.
        limit_bars: If > 0, stop after N bars (quick smoke test).
        quiet: Suppress strategy print output.

    Returns:
        A JSON-serializable dict of results.
    """
    import backtrader as bt

    overrides = {**TUNEABLE_PARAMS, **(params or {})}

    mod = load_strategy_module()

    # Monkey-patch to stop early when limit_bars is used.
    if limit_bars > 0:
        orig_next = mod.SunriseOgle.next

        def limited_next(self):
            if len(self.data) >= limit_bars:
                self.env.runstop()
                return
            orig_next(self)

        mod.SunriseOgle.next = limited_next

    feed_kwargs = dict(
        dataname=str(DATA_FILE),
        dtformat="%Y%m%d",
        tmformat="%H:%M:%S",
        datetime=0,
        time=1,
        open=2,
        high=3,
        low=4,
        close=5,
        volume=6,
        timeframe=bt.TimeFrame.Minutes,
        compression=5,
    )
    data = bt.feeds.GenericCSVData(**feed_kwargs)

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(data)
    cerebro.broker.setcash(starting_cash)
    cerebro.broker.setcommission(leverage=30.0)
    cerebro.addstrategy(mod.SunriseOgle, plot_result=False, print_signals=False, **overrides)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", timeframe=bt.TimeFrame.Days, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

    started = time.time()
    if quiet:
        with contextlib.redirect_stdout(io.StringIO()):
            results = cerebro.run()
    else:
        results = cerebro.run()
    elapsed = time.time() - started

    strat = results[0]
    final_value = cerebro.broker.getvalue()

    sharpe_analysis = strat.analyzers.sharpe.get_analysis()
    drawdown_analysis = strat.analyzers.drawdown.get_analysis()
    trade_analysis = strat.analyzers.trades.get_analysis()

    sharpe = sharpe_analysis.get("sharperatio")
    if sharpe is None:
        sharpe = 0.0

    max_dd_raw = drawdown_analysis.get("max", {}).get("drawdown", 0)
    if abs(max_dd_raw) <= 1.0:
        max_dd_pct = abs(max_dd_raw) * 100
    else:
        max_dd_pct = abs(max_dd_raw)

    total_trades = trade_analysis.get("total", {}).get("total", 0)
    won = trade_analysis.get("won", {}).get("total", 0)
    lost = trade_analysis.get("lost", {}).get("total", 0)

    gross_profit = trade_analysis.get("won", {}).get("pnl", {}).get("total", 0)
    gross_loss = abs(trade_analysis.get("lost", {}).get("pnl", {}).get("total", 0))
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    win_rate = (won / total_trades * 100) if total_trades > 0 else 0.0
    total_return_pct = ((final_value / starting_cash) - 1) * 100 if starting_cash else 0.0

    result = {
        "strategy_name": "SunriseOgle XAUUSD Pullback",
        "symbol": "XAUUSD",
        "timeframe": "5m",
        "framework": "backtrader",
        "status": "success",
        "metrics": {
            "total_return_pct": round(total_return_pct, 2),
            "final_value": round(final_value, 2),
            "total_pnl": round(final_value - starting_cash, 2),
            "sharpe_ratio": round(float(sharpe), 4),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else None,
            "trades": total_trades,
            "wins": won,
            "losses": lost,
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "expectancy": round(win_rate / 100 * (gross_profit / won) - (1 - win_rate / 100) * (gross_loss / lost), 2)
            if won and lost else 0.0,
        },
        "params": {k: v for k, v in overrides.items()},
        "config": {
            "starting_cash": starting_cash,
            "data_file": DATA_FILE.name,
            "limit_bars": limit_bars,
        },
        "elapsed_seconds": round(elapsed, 2),
        "updated": datetime.now(timezone.utc).isoformat(),
    }
    return result


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
        "available": strategy_available(),
        "repo_dir": str(REPO_DIR),
        "data_file": str(DATA_FILE),
        "has_cached_results": cached is not None,
        "results": cached,
    }


if __name__ == "__main__":
    # CLI smoke test
    import json as _json

    r = run_backtest(quiet=True)
    print(_json.dumps(r["metrics"], indent=2))