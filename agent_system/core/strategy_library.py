"""Strategy Library — onboarded trading strategies, backtests and metadata.

Each strategy is a pure function of OHLCV candles + parameters, so it can be
backtested/optimised here and (for signal strategies) deployed via the
execution engine. Sources are cited where a strategy follows a published
methodology or repository.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Strategy metadata (id -> definition). Reused by the bridge endpoint and the
# UI "Strategy Library" section so the on-screen list always matches backends.
# ─────────────────────────────────────────────────────────────────────────────
STRATEGIES: Dict[str, Dict[str, Any]] = {
    "ma_cross": {
        "name": "Moving Average Crossover",
        "short": "MA Cross",
        "class": "trend",
        "source": "Classic technical analysis (Pring, 2002)",
        "repo": None,
        "params": {"fast": 10, "slow": 30, "starting_cash": 10000},
        "description": "Goes long when the fast moving average crosses above the slow one, exits on the reverse cross. Captures persistent trends.",
        "assets": ["BTC", "ETH", "SOL", "XAU", "XRP"],
        "risk": "Medium",
        "timeframes": ["15m", "1h", "4h", "1d"],
    },
    "rsi": {
        "name": "RSI Mean Reversion",
        "short": "RSI",
        "class": "mean_reversion",
        "source": "Wilder (1978) — New Concepts in Technical Trading Systems",
        "repo": None,
        "params": {"period": 14, "overbought": 70, "oversold": 30, "starting_cash": 10000},
        "description": "Buys when RSI drops below the oversold band, sells when it rises above the overbought band. Classic counter-trend.",
        "assets": ["BTC", "ETH", "SOL", "XAU", "XRP", "MEME"],
        "risk": "Medium",
        "timeframes": ["15m", "1h", "4h", "1d"],
    },
    "rsi2": {
        "name": "RSI-2 Short-Term Reversion",
        "short": "RSI2",
        "class": "mean_reversion",
        "source": "Connors & Alvarez (2009) — Short Term Trading Strategies That Work",
        "repo": None,
        "params": {"period": 2, "buy_threshold": 10, "sell_threshold": 50, "starting_cash": 10000},
        "description": "Trades a fast RSI(2) oscillator: buys extreme dips (RSI<10) and takes the mean-reversion exit at RSI>50. Very short-horizon.",
        "assets": ["BTC", "ETH", "SOL", "XRP", "MEME"],
        "risk": "High",
        "timeframes": ["5m", "15m", "1h"],
    },
    "macd": {
        "name": "MACD Momentum",
        "short": "MACD",
        "class": "momentum",
        "source": "Appel (1979) — technical momentum oscillator",
        "repo": None,
        "params": {"fast": 12, "slow": 26, "signal": 9, "starting_cash": 10000},
        "description": "Long when the MACD line crosses above its signal line, flat on the reverse cross. Strong trend/momentum capture.",
        "assets": ["BTC", "ETH", "SOL", "XAU", "XRP"],
        "risk": "Medium",
        "timeframes": ["1h", "4h", "1d"],
    },
    "bb_reversion": {
        "name": "Bollinger Band Reversion",
        "short": "BB Rev",
        "class": "mean_reversion",
        "source": "Bollinger (2001) — Bollinger on Bollinger Bands",
        "repo": None,
        "params": {"period": 20, "dev": 2.0, "exit_mid": True, "starting_cash": 10000},
        "description": "Buys when price pokes below the lower Bollinger band, exits as price reverts to the middle band. Bet on mean reversion.",
        "assets": ["BTC", "ETH", "SOL", "XAU", "XRP", "MEME"],
        "risk": "Medium",
        "timeframes": ["15m", "1h", "4h"],
    },
    "donchian": {
        "name": "Donchian Channel Breakout",
        "short": "Donchian",
        "class": "breakout",
        "source": "Turtle trading system (Richard Dennis / William Eckhardt)",
        "repo": None,
        "params": {"entry": 20, "exit": 10, "atr_period": 14, "risk_pct": 1.0, "starting_cash": 10000},
        "description": "Turtle-style breakout: long when price breaks the N-period Donchian high, exit on the M-period low. Trend + ATR-based exits.",
        "assets": ["BTC", "ETH", "SOL", "XAU", "XRP", "MEME"],
        "risk": "Medium",
        "timeframes": ["1h", "4h", "1d"],
    },
    "stoch": {
        "name": "Stochastic Oscillator",
        "short": "Stoch",
        "class": "mean_reversion",
        "source": "Lane (1984) — %K/%D stochastic",
        "repo": None,
        "params": {"k": 14, "d": 3, "overbought": 80, "oversold": 20, "starting_cash": 10000},
        "description": "Buys when the fast stochastic crosses back above oversold, exits when it crosses below overbought.",
        "assets": ["BTC", "ETH", "SOL", "XAU", "XRP", "MEME"],
        "risk": "Medium",
        "timeframes": ["15m", "1h", "4h"],
    },
    "keltner": {
        "name": "Keltner Channel Breakout",
        "short": "Keltner",
        "class": "breakout",
        "source": "Chester Keltner (1960) — How to Make Money in Commodities",
        "repo": None,
        "params": {"period": 20, "mult": 2.0, "atr_period": 14, "starting_cash": 10000},
        "description": "Long when price closes above the upper Keltner channel (EMA ± ATR), exit when it closes back below the middle. ATR-scaled trend.",
        "assets": ["BTC", "ETH", "SOL", "XAU", "XRP"],
        "risk": "Medium",
        "timeframes": ["1h", "4h", "1d"],
    },
    "parabolic_sar": {
        "name": "Parabolic SAR",
        "short": "PSAR",
        "class": "trend",
        "source": "Wilder (1978) — Parabolic SAR",
        "repo": None,
        "params": {"step": 0.02, "max_step": 0.2, "starting_cash": 10000},
        "description": "Wilder's Parabolic SAR trailing-stop trend system: long while price holds above the SAR arc, flips when price closes through it.",
        "assets": ["BTC", "ETH", "SOL", "XAU", "XRP"],
        "risk": "High",
        "timeframes": ["1h", "4h", "1d"],
    },
    "ichimoku": {
        "name": "Ichimoku Cloud",
        "short": "Ichimoku",
        "class": "trend",
        "source": "Hosoda Goichi (1969) — Ichimoku Kinko Hyo",
        "repo": None,
        "params": {"tenkan": 9, "kijun": 26, "senkou_b": 52, "starting_cash": 10000},
        "description": "Long when price is above the cloud and Tenkan crosses above Kijun; exits on the reverse cross. Multi-timeframe trend system.",
        "assets": ["BTC", "ETH", "SOL", "XAU", "XRP"],
        "risk": "Medium",
        "timeframes": ["4h", "1d"],
    },
    "scalping_meme": {
        "name": "Meme Scalping",
        "short": "Scalp",
        "class": "momentum",
        "source": "In-house momentum scalper",
        "repo": None,
        "params": {"period": 20, "starting_cash": 10000},
        "description": "Short-term momentum on high-beta meme coins: long when price crosses above its fast MA, exit on reverse cross. High turnover.",
        "assets": ["MEME"],
        "risk": "High",
        "timeframes": ["15m", "1h"],
    },
    "short_meme": {
        "name": "Shorting Meme Coins",
        "short": "Short",
        "class": "momentum",
        "source": "In-house contrarian short bias",
        "repo": None,
        "params": {"period": 20, "starting_cash": 10000},
        "description": "Daily-timeframe short bias on overextended meme coins: short when price crosses below the 20-period MA, cover on reversal.",
        "assets": ["MEME"],
        "risk": "High",
        "timeframes": ["1d"],
    },
}

DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "XAU", "XRP", "MEME"]


def get_strategy(sid: str) -> Optional[Dict[str, Any]]:
    return STRATEGIES.get(sid)


def list_strategies() -> List[Dict[str, Any]]:
    out = []
    for sid, meta in STRATEGIES.items():
        m = dict(meta)
        m["id"] = sid
        out.append(m)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Indicators
# ─────────────────────────────────────────────────────────────────────────────
def _sma(vals: List[float], period: int) -> Optional[float]:
    if len(vals) < period:
        return None
    return sum(vals[-period:]) / period


def _ema(vals: List[float], period: int) -> float:
    if not vals:
        return 0.0
    k = 2.0 / (period + 1)
    ema = vals[0]
    for v in vals[1:]:
        ema = v * k + ema * (1 - k)
    return ema


def _rsi(closes: List[float], period: int) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(len(closes) - period, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - 100.0 / (1.0 + rs)


def _atr(candles: List[Dict], period: int) -> Optional[float]:
    if len(candles) < period:
        return None
    trs = []
    for i in range(len(candles) - period, len(candles)):
        c = candles[i]
        pc = candles[i - 1]
        hi, lo, cl, pcl = c["high"], c["low"], c["close"], pc["close"]
        tr = max(hi - lo, abs(hi - pcl), abs(lo - pcl))
        trs.append(tr)
    return sum(trs) / period


def _stoch(candles: List[Dict], k: int) -> Optional[float]:
    if len(candles) < k:
        return None
    seg = candles[-k:]
    hi = max(c["high"] for c in seg)
    lo = min(c["low"] for c in seg)
    rng = hi - lo
    if rng <= 0:
        return 50.0
    return (candles[-1]["close"] - lo) / rng * 100.0


# ─────────────────────────────────────────────────────────────────────────────
# Backtest engine
# ─────────────────────────────────────────────────────────────────────────────
class BacktestEngine:
    """Vectorized-ish bar-by-bar backtester. Supports long-only strategies.

    `candles`: list of dicts with open/high/low/close/volume (+ts).
    Returns metrics compatible with the bridge/UI (total_return_pct,
    max_drawdown_pct, trades, win_rate, sharpe, final_equity).
    """

    def __init__(self, candles: List[Dict], params: Dict[str, Any]):
        self.candles = candles
        self.params = params or {}
        self.cash = float(self.params.get("starting_cash", 10000))
        self.starting = self.cash
        self.pos = 0          # 0 flat, 1 long
        self.entry = 0.0
        self.entry_price = 0.0
        self.trades = 0
        self.wins = 0
        self.equity = [self.cash]

    # --- indicator helpers returning series-friendly values at index i -------
    def _sma_at(self, closes: List[float], i: int, period: int) -> float:
        return sum(closes[i - period:i]) / period

    def run(self, sid: str) -> Dict[str, Any]:
        closes = [c["close"] for c in self.candles]
        n = len(closes)
        strat = STRATEGIES.get(sid, {})
        for i in range(1, n):
            signal = self._signal(sid, closes, i)
            price = closes[i]
            if signal == 1 and self.pos == 0:
                self.pos = 1
                self.entry = price
                self.entry_price = price
            elif signal == -1 and self.pos == 1:
                ret = (price - self.entry_price) / self.entry_price
                self.cash *= (1 + ret)
                if ret > 0:
                    self.wins += 1
                self.trades += 1
                self.pos = 0
            if self.pos == 1:
                self.equity.append(self.cash * (1 + (price - self.entry_price) / self.entry_price))
            else:
                self.equity.append(self.cash)
        if self.pos == 1:
            self.trades += 1
            self.equity.append(self.cash * (1 + (closes[-1] - self.entry_price) / self.entry_price))
        return self._metrics(sid)

    def _metrics(self, sid: str) -> Dict[str, Any]:
        final = self.equity[-1]
        total_ret = (final / self.starting - 1) * 100
        peak = max(self.equity, default=self.starting)
        mdd = (peak - min(self.equity)) / peak * 100 if peak > 0 else 0
        win_rate = (self.wins / self.trades * 100) if self.trades > 0 else 0
        sharpe = (total_ret / mdd) if mdd > 0 else 0
        return {
            "strategy_id": sid,
            "starting_cash": self.starting,
            "final_equity": round(final, 2),
            "total_return_pct": round(total_ret, 2),
            "max_drawdown_pct": round(mdd, 2),
            "trades": self.trades,
            "win_rate": round(win_rate, 1),
            "sharpe": round(sharpe, 2),
        }

    # --- signal generation ---------------------------------------------------
    def _signal(self, sid: str, closes: List[float], i: int) -> int:
        p = self.params
        if sid == "ma_cross":
            fast = int(p.get("fast", 10))
            slow = int(p.get("slow", 30))
            if i < slow:
                return 0
            mf = self._sma_at(closes, i, fast)
            ms = self._sma_at(closes, i, slow)
            pf = self._sma_at(closes, i - 1, fast)
            ps = self._sma_at(closes, i - 1, slow)
            if mf > ms and pf <= ps:
                return 1
            if mf < ms and pf >= ps:
                return -1
            return 0
        if sid == "rsi":
            period = int(p.get("period", 14))
            ob = float(p.get("overbought", 70))
            os = float(p.get("oversold", 30))
            if i < period:
                return 0
            val = _rsi(closes[:i + 1], period)
            prev = _rsi(closes[:i], period)
            if prev is None or val is None:
                return 0
            if val < os and prev >= os:
                return 1
            if val > ob and prev <= ob:
                return -1
            return 0
        if sid == "rsi2":
            period = max(2, int(p.get("period", 2)))
            buy = float(p.get("buy_threshold", 10))
            sell = float(p.get("sell_threshold", 50))
            if i < period + 2:
                return 0
            val = _rsi(closes[:i + 1], period)
            prev = _rsi(closes[:i], period)
            if prev is None or val is None:
                return 0
            if val < buy and prev >= buy:
                return 1
            if val > sell and prev <= sell:
                return -1
            return 0
        if sid == "macd":
            fast = int(p.get("fast", 12))
            slow = int(p.get("slow", 26))
            sig = int(p.get("signal", 9))
            if i < slow + sig + 2:
                return 0
            macd_now = _ema(closes[:i + 1], fast) - _ema(closes[:i + 1], slow)
            macd_prev = _ema(closes[:i], fast) - _ema(closes[:i], slow)
            # signal line = EMA(sig) of the macd series
            macd_series = [_ema(closes[:j + 1], fast) - _ema(closes[:j + 1], slow) for j in range(i - sig, i + 1)]
            s_now = _ema(macd_series, sig)
            macd_series_p = [_ema(closes[:j + 1], fast) - _ema(closes[:j + 1], slow) for j in range(i - sig - 1, i)]
            s_prev = _ema(macd_series_p, sig) if len(macd_series_p) >= sig else macd_prev
            if macd_now > s_now and macd_prev <= s_prev:
                return 1
            if macd_now < s_now and macd_prev >= s_prev:
                return -1
            return 0
        if sid == "bb_reversion":
            period = int(p.get("period", 20))
            dev = float(p.get("dev", 2.0))
            exit_mid = bool(p.get("exit_mid", True))
            if i < period:
                return 0
            seg = closes[i - period:i]
            mid = self._sma_at(closes, i, period)
            sd = (sum((x - mid) ** 2 for x in seg) / period) ** 0.5
            lower = mid - dev * sd
            upper = mid + dev * sd
            price = closes[i]
            prev = closes[i - 1]
            if price < lower and prev >= lower:
                return 1
            if self.pos == 1:
                if exit_mid and price >= mid:
                    return -1
                if not exit_mid and price >= upper:
                    return -1
            return 0
        if sid == "donchian":
            entry = int(p.get("entry", 20))
            exitp = int(p.get("exit", 10))
            if i <= entry:
                return 0
            price = closes[i]
            prev = closes[i - 1]
            hi_entry = max(closes[i - entry:i])
            hi_prev = max(closes[i - entry - 1:i - 1])
            lo_exit = min(closes[i - exitp:i])
            if price > hi_entry and prev <= hi_prev:
                return 1
            if self.pos == 1 and price < lo_exit:
                return -1
            return 0
        if sid == "stoch":
            k = int(p.get("k", 14))
            d = int(p.get("d", 3))
            ob = float(p.get("overbought", 80))
            os = float(p.get("oversold", 20))
            if i < k + d:
                return 0
            k_now = _stoch(self.candles[:i + 1], k)
            k_prev = _stoch(self.candles[:i], k)
            if k_now is None or k_prev is None:
                return 0
            if k_now < os and k_prev >= os:
                return 1
            if k_now > ob and k_prev <= ob:
                return -1
            return 0
        if sid == "keltner":
            period = int(p.get("period", 20))
            mult = float(p.get("mult", 2.0))
            atr_p = int(p.get("atr_period", 14))
            if i < max(period, atr_p) + 1:
                return 0
            ema = _ema(closes[:i + 1], period)
            ema_prev = _ema(closes[:i], period)
            atr = _atr(self.candles[:i + 1], atr_p)
            if atr is None:
                return 0
            upper = ema + mult * atr
            lower = ema - mult * atr
            price, prev = closes[i], closes[i - 1]
            if price > upper and prev <= _ema(closes[:i], period) + mult * _atr(self.candles[:i], atr_p):
                return 1
            if self.pos == 1 and price < ema_prev:
                return -1
            return 0
        if sid == "parabolic_sar":
            step = float(p.get("step", 0.02))
            max_step = float(p.get("max_step", 0.2))
            if i < 2:
                return 0
            sar = closes[i - 1]
            ep = closes[i - 1]
            af = step
            rising = True
            price, prev = closes[i], closes[i - 1]
            for j in range(max(1, i - 20), i):
                if rising:
                    sar = sar + af * (ep - sar)
                    if prev < closes[j]:
                        ep = closes[j]
                        af = min(af + step, max_step)
                    elif prev > sar:
                        rising = False
                        sar = ep
                        ep = prev
                        af = step
                else:
                    sar = sar + af * (ep - sar)
                    if prev > closes[j]:
                        ep = closes[j]
                        af = min(af + step, max_step)
                    elif prev < sar:
                        rising = True
                        sar = ep
                        ep = prev
                        af = step
            if rising and price > sar and prev <= sar:
                return 1
            if rising and price < sar:
                return -1
            return 0
        if sid in ("scalping_meme", "short_meme"):
            period = int(p.get("period", 20))
            if i < period:
                return 0
            ma = self._sma_at(closes, i, period)
            ma_prev = self._sma_at(closes, i - 1, period)
            price, prev = closes[i], closes[i - 1]
            if sid == "scalping_meme":
                if price > ma and prev <= ma_prev:
                    return 1
                if price < ma and prev >= ma_prev:
                    return -1
            else:
                if price < ma and prev >= ma_prev:
                    return 1
                if price > ma and prev <= ma_prev:
                    return -1
            return 0
        return 0


def run_backtest(sid: str, candles: List[Dict], params: Dict[str, Any]) -> Dict[str, Any]:
    eng = BacktestEngine(candles, params)
    return eng.run(sid)


# ─────────────────────────────────────────────────────────────────────────────
# Parameter optimisation — grid search over a param, returns sorted results.
# ─────────────────────────────────────────────────────────────────────────────
def optimize(sid: str, candles: List[Dict], base: Dict[str, Any],
             grid: Dict[str, List[float]], metric: str = "total_return_pct",
             top: int = 5) -> List[Dict[str, Any]]:
    """Grid-search `grid` (param -> candidate values) over `base`, returning
    the best combinations ranked by `metric`. Useful for tuning a strategy to
    a specific asset/timeframe."""
    import itertools
    results = []
    params = dict(base)
    combos = list(itertools.product(*grid.values()))
    for combo in combos:
        test = dict(params)
        test.update(zip(grid.keys(), combo))
        try:
            m = run_backtest(sid, candles, test)
            results.append({"params": test, "metrics": m})
        except Exception:
            continue
    results.sort(key=lambda r: r["metrics"].get(metric, -1e18), reverse=True)
    return results[:top]


# ─────────────────────────────────────────────────────────────────────────────
# Param specification catalog — every parameter the backtest engine accepts,
# with type, default, min/max and a human-readable description. Drives the
# "strategy spec" output for natural-language strategy descriptions.
# ─────────────────────────────────────────────────────────────────────────────
PARAM_SPECS: Dict[str, Dict[str, Any]] = {
    "fast": {"type": "int", "default": 12, "min": 2, "max": 200,
             "description": "Fast EMA/SMA period for the short signal."},
    "slow": {"type": "int", "default": 26, "min": 5, "max": 400,
             "description": "Slow EMA/SMA period for the long signal."},
    "signal": {"type": "int", "default": 9, "min": 2, "max": 100,
               "description": "Signal-line smoothing period (MACD)."},
    "period": {"type": "int", "default": 14, "min": 2, "max": 200,
               "description": "Lookback period of the indicator."},
    "overbought": {"type": "float", "default": 70, "min": 50, "max": 100,
                   "description": "Indicator level that triggers the exit (sell)."},
    "oversold": {"type": "float", "default": 30, "min": 0, "max": 50,
                 "description": "Indicator level that triggers the entry (buy)."},
    "buy_threshold": {"type": "float", "default": 10, "min": 1, "max": 40,
                      "description": "RSI-2 level that triggers a buy (deep oversold zone)."},
    "sell_threshold": {"type": "float", "default": 50, "min": 30, "max": 90,
                       "description": "RSI-2 exit level once mean reversion is complete."},
    "dev": {"type": "float", "default": 2.0, "min": 0.5, "max": 5.0,
            "description": "Number of standard deviations for the Bollinger bands."},
    "exit_mid": {"type": "bool", "default": True,
                 "description": "Exit at the middle band (true) or the upper band (false)."},
    "entry": {"type": "int", "default": 20, "min": 5, "max": 200,
              "description": "Donchian entry lookback (N-bar high breakout)."},
    "exit": {"type": "int", "default": 10, "min": 3, "max": 100,
             "description": "Donchian exit lookback (M-bar low)."},
    "atr_period": {"type": "int", "default": 14, "min": 5, "max": 100,
                   "description": "ATR averaging period for volatility scaling."},
    "risk_pct": {"type": "float", "default": 1.0, "min": 0.1, "max": 20.0,
                 "description": "Per-trade risk as a percentage of equity."},
    "k": {"type": "int", "default": 14, "min": 3, "max": 100,
          "description": "Stochastic %K lookback period."},
    "d": {"type": "int", "default": 3, "min": 2, "max": 50,
          "description": "Stochastic %D smoothing period."},
    "mult": {"type": "float", "default": 2.0, "min": 0.5, "max": 8.0,
             "description": "Keltner channel ATR multiplier."},
    "step": {"type": "float", "default": 0.02, "min": 0.001, "max": 0.2,
             "description": "Parabolic SAR acceleration factor initial value."},
    "max_step": {"type": "float", "default": 0.2, "min": 0.01, "max": 1.0,
                 "description": "Parabolic SAR acceleration factor cap."},
    "tenkan": {"type": "int", "default": 9, "min": 3, "max": 60,
               "description": "Ichimoku Tenkan-sen (conversion line) period."},
    "kijun": {"type": "int", "default": 26, "min": 5, "max": 120,
              "description": "Ichimoku Kijun-sen (base line) period."},
    "senkou_b": {"type": "int", "default": 52, "min": 10, "max": 240,
                 "description": "Ichimoku Senkou B (leading span) period."},
    "starting_cash": {"type": "float", "default": 10000, "min": 100, "max": 100000000,
                      "description": "Initial capital for the backtest."},
}

# Regex rules used to pull numeric values out of a natural-language sentence.
# Keys are param names; the first rule in the list that matches wins.
_PARAM_PATTERNS: Dict[str, List[str]] = {
    "fast": [r"\bfast\b[^\d]{0,12}(\d+)"],
    "slow": [r"\bslow\b[^\d]{0,12}(\d+)"],
    "signal": [r"\bsignal\b[^\d]{0,10}(\d+)"],
    "period": [r"\b(\d+)\s*[- ]?period\b",
               r"\bperiod\b[^\d]{0,10}(\d+)",
               r"\brsi\b[^\d]{0,6}(\d+)",
               r"\brsi\s*\(\s*(\d+)\s*\)"],
    "overbought": [r"\boverbought\b[^\d]{0,12}(\d+)",
                   r"\b(?:above|over|exceed(?:s|ing)?)\s*(\d+)"],
    "oversold": [r"\boversold\b[^\d]{0,12}(\d+)",
                 r"\b(?:below|under)\s*(\d+)"],
    "buy_threshold": [r"\bbelow\s*(\d+)", r"\boversold\b[^\d]{0,12}(\d+)"],
    "sell_threshold": [r"\b(?:above|over|at)\s*(\d+)", r"\boverbought\b[^\d]{0,12}(\d+)"],
    "dev": [r"\bdeviation\b[^\d]{0,10}([\d.]+)",
            r"\bdev\b[^\d]{0,6}([\d.]+)",
            r"\b([\d.]+)\s*(?:std|standard\s*deviations?)\b"],
    "exit_mid": [r"\bmiddle\s*band\b|\bmid\s*band\b"],
    "entry": [r"\b(?:enter|entry)\b[^\d]{0,12}(\d+)"],
    "exit": [r"\b(?:exit|exits?)\b[^\d]{0,12}(\d+)"],
    "atr_period": [r"\batr\b[^\d]{0,8}(\d+)"],
    "risk_pct": [r"\brisk\b[^\d]{0,10}([\d.]+)\s*%?"],
    "k": [r"%?\s*k\s*[=:]\s*(\d+)", r"\bstoch(?:astic)?\b[^\d]{0,8}(\d+)"],
    "d": [r"%?\s*d\s*[=:]\s*(\d+)"],
    "mult": [r"\b([\d.]+)\s*[- ]?multipliers?\b", r"\bmultiplier\b[^\d]{0,8}([\d.]+)", r"\bkeltner\b[^\d]{0,8}([\d.]+)"],
    "step": [r"\bstep\b[^\d]{0,12}([\d.]+)"],
    "max_step": [r"\bmax(?:imum)?\s*[- ]?step\b[^\d]{0,8}([\d.]+)"],
    "tenkan": [r"\btenkan\b[^\d]{0,8}(\d+)"],
    "kijun": [r"\bkijun\b[^\d]{0,8}(\d+)"],
    "senkou_b": [r"\bsenkou\b[^\d]{0,8}(\d+)", r"\bcloud\b[^\d]{0,8}(\d+)"],
    "starting_cash": [r"\b([\d,]+)\s*(?:usd)?\s*capital\b",
                      r"\b(?:capital|cash|amount)\b[^\d]{0,12}([\d,]+)"],
}

_ASSET_WORDS = {"btc": "BTC", "bitcoin": "BTC", "eth": "ETH", "ethereum": "ETH",
                "sol": "SOL", "solana": "SOL", "xau": "XAU", "gold": "XAU",
                "xrp": "XRP", "ripple": "XRP", "doge": "DOGE", "memecoin": "MEME",
                "meme": "MEME", "memes": "MEME", "pepe": "MEME", "shib": "MEME",
                "wif": "MEME"}
_TF_PATTERN = re.compile(r"\b(5m|15m|30m|1h|2h|4h|1d|1w)\b")

_DETECT_RULES: List[tuple] = [
    ("rsi2", re.compile(r"\b(rsi[- ]?2|rsi2|connors[- ]2)\b")),
    ("rsi", re.compile(r"\brsi\b")),
    ("macd", re.compile(r"\bmacd\b")),
    ("bb_reversion", re.compile(r"\bbollinger\b|\bbands\b")),
    ("donchian", re.compile(r"\bdonchian\b|\bturtle\b")),
    ("keltner", re.compile(r"\bkeltner\b")),
    ("stoch", re.compile(r"\bstoch(?:astic)?\b")),
    ("ichimoku", re.compile(r"\bichimoku\b|\bcloud\b")),
    ("parabolic_sar", re.compile(r"\bparabolic\s*sar\b|\bpsar\b")),
    ("scalping_meme", re.compile(r"\bmomentum\s*(scalp|meme|coin)\b|\bscalp\b|\bvolume\s*surge\b")),
    ("short_meme", re.compile(r"\bfade[s]?\s*(the\s*)?pump\b|\bshort\s*(the\s*)?meme\b|\boverextended\b")),
    ("ma_cross", re.compile(r"\bma[- ]?cross|cross(?:ing)?\s*(over|of)?\s*(a )?(moving\s*)?averages?|moving\s*average\s*cross|crossover\b")),
]


def _detect_strategy(text: str) -> Optional[str]:
    """Pick the best-matching onboarded strategy for a natural-language sentence."""
    t = text.lower()
    for sid, rx in _DETECT_RULES:
        if rx.search(t):
            return sid
    return None


def _clamp(name: str, value: float, default: float) -> float:
    spec = PARAM_SPECS.get(name, {})
    lo = spec.get("min"); hi = spec.get("max")
    if lo is not None and value < lo:
        return float(lo)
    if hi is not None and value > hi:
        return float(hi)
    return value


def generate_strategy_spec(description: str) -> Dict[str, Any]:
    """Translate a plain-English strategy description into a full engine-ready
    parameter specification.

    Output includes every parameter the strategy accepts (type, default, valid
    range, description), any values inferred from the sentence, and a ready-made
    ``backtest_request`` body that can be POSTed straight to /backtest/run.
    """
    desc = (description or "").strip()
    text = desc.lower()
    sid = _detect_strategy(text) or "ma_cross"
    meta = STRATEGIES[sid]
    defaults = dict(meta["params"])

    detected, notes = {}, []
    for pname in defaults:
        if pname not in _PARAM_PATTERNS:
            continue
        sp = PARAM_SPECS.get(pname, {})
        for pat in _PARAM_PATTERNS[pname]:
            if sp.get("type") == "bool":
                if re.search(pat, text):
                    detected[pname] = True
                    notes.append(f'inferred {pname}=true from "{re.search(pat, text).group(0).strip()}"')
                continue
            m = re.search(pat, text)
            if m:
                raw = m.group(1)
                raw = raw.replace(",", "")
                try:
                    val = float(raw) if sp.get("type") == "float" else int(float(raw))
                except ValueError:
                    continue
                detected[pname] = val
                notes.append(f'inferred {pname}={val} from "{m.group(0).strip()}"')
                break

    # Pairwise "12/26/9" MACD syntax (fallback, no keywords needed)
    if sid == "macd" and not detected.get("fast"):
        m = re.search(r"\b(\d{1,3})\s*[/,;]\s*(\d{1,3})\s*[/,;]\s*(\d{1,3})\b", text)
        if m:
            detected.update({"fast": int(m.group(1)), "slow": int(m.group(2)), "signal": int(m.group(3))})
            notes.append(f"inferred MACD fast/slow/signal = {m.group(1)}/{m.group(2)}/{m.group(3)}")
    # Pairwise "20/10" Donchian syntax
    if sid == "donchian" and not detected.get("entry"):
        m = re.search(r"\b(\d{1,2})\s*[/,;]\s*(\d{1,2})\b", text)
        if m:
            detected.update({"entry": int(m.group(1)), "exit": int(m.group(2))})
            notes.append(f"inferred Donchian entry/exit = {m.group(1)}/{m.group(2)}")

    # Asset + timeframe hints
    asset_hint = None
    for word, code in _ASSET_WORDS.items():
        if re.search(r"\b" + word + r"\b", text):
            asset_hint = code
            break
    tf_m = _TF_PATTERN.search(text)
    tf_hint = tf_m.group(1) if tf_m else None

    # Build the final params + per-param spec rows
    final = {}
    spec_rows = []
    for pname, default in defaults.items():
        p_spec = dict(PARAM_SPECS.get(pname, {"type": "auto", "description": "", "min": None, "max": None}))
        default = p_spec.get("default", default)
        if pname in detected:
            val = _clamp(pname, detected[pname], default)
            final[pname] = val
        else:
            final[pname] = default
        p_spec.update({
            "name": pname,
            "default": default,
            "detected": detected.get(pname),
            "value": final[pname],
            "changed": pname in detected,
        })
        spec_rows.append(p_spec)

    asset = asset_hint or (meta["assets"][0] if meta.get("assets") else "BTC")
    tf = tf_hint or (meta["timeframes"][0] if meta.get("timeframes") else "1h")

    return {
        "description": desc,
        "strategy_id": sid,
        "name": meta["name"],
        "short": meta.get("short"),
        "class": meta.get("class"),
        "risk": meta.get("risk"),
        "source": meta.get("source"),
        "matched": sid != "ma_cross" or _detect_strategy(desc) == "ma_cross",
        "asset": asset,
        "timeframe": tf,
        "params": final,
        "param_specs": spec_rows,
        "backtest_request": {
            "strategy": sid,
            "asset": asset,
            "timeframe": tf,
            "limit": 500,
            "params": final,
        },
        "notes": notes if notes else ["using default parameters — none inferred from the description"],
    }
