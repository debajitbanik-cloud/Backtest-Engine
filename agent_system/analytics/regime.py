"""
Regime Detection — trend, mean reversion, volatility, liquidity, momentum, session, stress.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


class RegimeType(str, Enum):
    TREND = "trend"
    MEAN_REVERSION = "mean_reversion"
    VOLATILITY = "volatility"
    LIQUIDITY = "liquidity"
    MOMENTUM = "momentum"
    SESSION = "session"
    STRESS = "stress"


class TrendDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    SIDEWAYS = "sideways"


class VolatilityRegime(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EXTREME = "extreme"


class LiquidityRegime(str, Enum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    DRY = "dry"


class StressLevel(str, Enum):
    CALM = "calm"
    ELEVATED = "elevated"
    STRESS = "stress"
    CRISIS = "crisis"


@dataclass
class RegimeState:
    """Complete regime state across all dimensions."""
    timestamp: datetime
    # Trend
    trend_direction: TrendDirection = TrendDirection.SIDEWAYS
    trend_strength: float = 0.0  # 0-1
    trend_duration: int = 0  # bars
    # Volatility
    volatility_regime: VolatilityRegime = VolatilityRegime.NORMAL
    realized_vol: float = 0.0
    implied_vol: Optional[float] = None
    vol_percentile: float = 0.5  # 0-1 percentile
    # Liquidity
    liquidity_regime: LiquidityRegime = LiquidityRegime.NORMAL
    spread_pct: float = 0.0
    depth: float = 0.0
    # Momentum
    momentum_score: float = 0.0  # -1 to 1
    rsi: float = 50.0
    macd_signal: float = 0.0
    # Session
    session: str = "unknown"  # asia, europe, us, overlap
    session_progress: float = 0.0  # 0-1 within session
    # Stress
    stress_level: StressLevel = StressLevel.CALM
    stress_score: float = 0.0  # 0-1
    drawdown_pct: float = 0.0
    correlation_breakdown: bool = False
    # Composite
    dominant_regime: RegimeType = RegimeType.TREND
    confidence: float = 0.5


class RegimeDetector:
    """
    Multi-dimensional regime detection:
    - Trend (direction, strength, duration)
    - Volatility (level, percentile, regime)
    - Liquidity (spread, depth, regime)
    - Momentum (RSI, MACD, custom score)
    - Session (time-of-day, overlap detection)
    - Stress (drawdown, correlation breakdown, vol spike)
    """

    def __init__(
        self,
        trend_lookback: int = 200,
        vol_lookback: int = 50,
        vol_percentile_window: int = 252,
        momentum_lookback: int = 14,
        session_timezone: str = "UTC",
    ):
        self.trend_lookback = trend_lookback
        self.vol_lookback = vol_lookback
        self.vol_percentile_window = vol_percentile_window
        self.momentum_lookback = momentum_lookback
        self.session_timezone = session_timezone
        self._history: List[RegimeState] = []

    def detect(self, df: pd.DataFrame) -> RegimeState:
        """
        Detect current regime state from market data.
        Expects DataFrame with columns: open, high, low, close, volume (optional)
        with DatetimeIndex.
        """
        if df.empty:
            return RegimeState(timestamp=datetime.utcnow())

        latest = df.iloc[-1]
        timestamp = df.index[-1]

        # ── Trend Detection ──
        trend_direction, trend_strength, trend_duration = self._detect_trend(df)

        # ── Volatility ──
        volatility_regime, realized_vol, vol_percentile = self._detect_volatility(df)

        # ── Liquidity ──
        liquidity_regime, spread_pct, depth = self._detect_liquidity(df)

        # ── Momentum ──
        momentum_score, rsi, macd_signal = self._detect_momentum(df)

        # ── Session ──
        session, session_progress = self._detect_session(timestamp)

        # ── Stress ──
        stress_level, stress_score, drawdown_pct, correlation_breakdown = self._detect_stress(df)

        # ── Dominant regime ──
        dominant_regime, confidence = self._determine_dominant_regime(
            trend_strength, vol_percentile, momentum_score, stress_score
        )

        state = RegimeState(
            timestamp=timestamp,
            trend_direction=trend_direction,
            trend_strength=trend_strength,
            trend_duration=trend_duration,
            volatility_regime=volatility_regime,
            realized_vol=realized_vol,
            vol_percentile=vol_percentile,
            liquidity_regime=liquidity_regime,
            spread_pct=spread_pct,
            depth=depth,
            momentum_score=momentum_score,
            rsi=rsi,
            macd_signal=macd_signal,
            session=session,
            session_progress=session_progress,
            stress_level=stress_level,
            stress_score=stress_score,
            drawdown_pct=drawdown_pct,
            correlation_breakdown=correlation_breakdown,
            dominant_regime=dominant_regime,
            confidence=confidence,
        )

        self._history.append(state)
        if len(self._history) > 1000:
            self._history = self._history[-1000:]

        return state

    def _detect_trend(self, df: pd.DataFrame) -> Tuple[TrendDirection, float, int]:
        """Detect trend direction, strength, and duration."""
        close = df["close"]
        if len(close) < self.trend_lookback:
            return TrendDirection.SIDEWAYS, 0.0, 0

        # SMA slope
        sma_short = close.rolling(20).mean()
        sma_long = close.rolling(50).mean()
        sma_slope = (sma_short - sma_long).iloc[-1] / close.iloc[-1]

        # ADX-style trend strength
        high = df["high"]
        low = df["low"]
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        adx_proxy = abs(sma_slope) / (atr / close.iloc[-1]) if atr > 0 else 0
        adx = min(adx_proxy * 100, 100)  # Scale to 0-100

        # Determine direction
        if sma_short.iloc[-1] > sma_long.iloc[-1] and adx > 25:
            direction = TrendDirection.UP
        elif sma_short.iloc[-1] < sma_long.iloc[-1] and adx > 25:
            direction = TrendDirection.DOWN
        else:
            direction = TrendDirection.SIDEWAYS

        # Duration
        duration = 0
        for i in range(2, min(50, len(close))):
            if direction == TrendDirection.UP:
                if close.iloc[-i] > close.iloc[-i-1]:
                    duration += 1
                else:
                    break
            elif direction == TrendDirection.DOWN:
                if close.iloc[-i] < close.iloc[-i-1]:
                    duration += 1
                else:
                    break
            else:
                break

        return direction, min(adx / 100, 1.0), duration

    def _detect_volatility(self, df: pd.DataFrame) -> Tuple[VolatilityRegime, float, float]:
        """Detect volatility regime and percentile."""
        close = df["close"]
        returns = close.pct_change().dropna()

        if len(returns) < self.vol_lookback:
            return VolatilityRegime.NORMAL, 0.0, 0.5

        # Realized volatility (annualized)
        realized_vol = returns.rolling(self.vol_lookback).std().iloc[-1] * np.sqrt(252)

        # Percentile
        if len(returns) >= self.vol_percentile_window:
            vol_series = returns.rolling(self.vol_lookback).std() * np.sqrt(252)
            vol_percentile = (vol_series <= realized_vol).mean()
        else:
            vol_percentile = 0.5

        # Regime classification
        if vol_percentile < 0.2:
            regime = VolatilityRegime.LOW
        elif vol_percentile < 0.8:
            regime = VolatilityRegime.NORMAL
        elif vol_percentile < 0.95:
            regime = VolatilityRegime.HIGH
        else:
            regime = VolatilityRegime.EXTREME

        return regime, realized_vol, vol_percentile

    def _detect_liquidity(self, df: pd.DataFrame) -> Tuple[LiquidityRegime, float, float]:
        """Detect liquidity regime from spread and depth."""
        if "volume" not in df.columns:
            return LiquidityRegime.NORMAL, 0.0, 0.0

        # Spread proxy: (high - low) / close
        spread_pct = ((df["high"] - df["low"]) / df["close"]).iloc[-1]
        # Depth proxy: volume
        depth = df["volume"].iloc[-1] if "volume" in df.columns else 0.0

        # Classify based on spread
        if spread_pct < 0.001:
            regime = LiquidityRegime.HIGH
        elif spread_pct < 0.005:
            regime = LiquidityRegime.NORMAL
        elif spread_pct < 0.01:
            regime = LiquidityRegime.LOW
        else:
            regime = LiquidityRegime.DRY

        return regime, spread_pct, depth

    def _detect_momentum(self, df: pd.DataFrame) -> Tuple[float, float, float]:
        """Detect momentum indicators."""
        close = df["close"]

        # RSI
        rsi = 50.0
        if len(close) >= 14:
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain / loss.replace(0, np.nan)
            rsi = (100 - (100 / (1 + rs))).iloc[-1]

        # MACD
        macd_signal = 0.0
        if len(close) >= 26:
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd = ema12 - ema26
            signal = macd.ewm(span=9, adjust=False).mean()
            macd_signal = (macd - signal).iloc[-1]

        # Momentum score: combine RSI and MACD
        momentum_score = 0.0
        if not np.isnan(rsi):
            momentum_score += (rsi - 50) / 50  # -1 to 1
        if not np.isnan(macd_signal):
            momentum_score += np.sign(macd_signal) * min(abs(macd_signal) * 100, 1)
        momentum_score = np.clip(momentum_score / 2, -1, 1)

        return momentum_score, rsi, macd_signal

    def _detect_session(self, timestamp: pd.Timestamp) -> Tuple[str, float]:
        """Detect trading session and progress within session."""
        # Convert to UTC if needed
        if timestamp.tz is None:
            timestamp = timestamp.tz_localize("UTC")
        else:
            timestamp = timestamp.tz_convert("UTC")

        hour = timestamp.hour
        minute = timestamp.minute

        # Session definitions (UTC)
        # Asia: 00-08, Europe: 08-16, US: 13-21, Overlap: 13-16
        if 0 <= hour < 8:
            session = "asia"
            progress = (hour * 60 + minute) / (8 * 60)
        elif 8 <= hour < 13:
            session = "europe"
            progress = ((hour - 8) * 60 + minute) / (5 * 60)
        elif 13 <= hour < 16:
            session = "overlap"
            progress = ((hour - 13) * 60 + minute) / (3 * 60)
        elif 13 <= hour < 21:
            session = "us"
            progress = ((hour - 13) * 60 + minute) / (8 * 60)
        else:
            session = "closed"
            progress = 0.0

        return session, progress

    def _detect_stress(self, df: pd.DataFrame) -> Tuple[StressLevel, float, float, bool]:
        """Detect stress regime."""
        close = df["close"]
        returns = close.pct_change().dropna()

        # Drawdown
        cummax = close.expanding().max()
        drawdown = (close - cummax) / cummax
        drawdown_pct = abs(drawdown.iloc[-1])

        # Vol spike
        vol_spike = False
        if len(returns) >= 20:
            recent_vol = returns.rolling(10).std().iloc[-1]
            normal_vol = returns.rolling(50).std().iloc[-1]
            vol_spike = recent_vol > normal_vol * 2

        # Correlation breakdown (placeholder - needs multi-asset)
        correlation_breakdown = False

        # Stress score
        stress_score = 0.0
        stress_score += min(drawdown_pct * 10, 1.0)  # 0-1 from drawdown
        stress_score += 0.5 if vol_spike else 0.0

        # Stress level
        if stress_score < 0.2:
            level = StressLevel.CALM
        elif stress_score < 0.5:
            level = StressLevel.ELEVATED
        elif stress_score < 0.8:
            level = StressLevel.STRESS
        else:
            level = StressLevel.CRISIS

        return level, stress_score, drawdown_pct, correlation_breakdown

    def _determine_dominant_regime(
        self,
        trend_strength: float,
        vol_percentile: float,
        momentum_score: float,
        stress_score: float,
    ) -> Tuple[RegimeType, float]:
        """Determine the dominant regime type."""
        scores = {
            RegimeType.TREND: trend_strength,
            RegimeType.VOLATILITY: vol_percentile,
            RegimeType.MOMENTUM: abs(momentum_score),
            RegimeType.STRESS: stress_score,
        }

        dominant = max(scores, key=scores.get)
        confidence = scores[dominant]

        return dominant, confidence

    def get_history(self, limit: int = 100) -> List[RegimeState]:
        """Get recent regime history."""
        return self._history[-limit:]


# Global detector
_regime_detector: Optional[RegimeDetector] = None


def get_regime_detector() -> RegimeDetector:
    global _regime_detector
    if _regime_detector is None:
        _regime_detector = RegimeDetector()
    return _regime_detector