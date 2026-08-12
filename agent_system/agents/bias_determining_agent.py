"""
Bias Determining Agent
Determines market bias (bullish/bearish/neutral) using multiple indicators.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Literal
from collections import deque
import numpy as np

from core.base_agent import BaseAgent, AgentConfig, AgentStatus
from core.event_bus import EventBus, Event, EventType, event_bus


BiasDirection = Literal["bullish", "bearish", "neutral"]


@dataclass
class BiasSignal:
    """Market bias signal with confidence."""
    symbol: str
    direction: BiasDirection
    confidence: float  # 0.0 to 1.0
    indicators: Dict[str, float]
    timestamp: datetime
    timeframe: str
    reasoning: str


@dataclass
class BiasConfig:
    """Configuration for bias determination."""
    timeframes: List[str] = field(default_factory=lambda: ["1m", "5m", "15m", "1h", "4h"])
    primary_timeframe: str = "15m"
    lookback_periods: int = 100
    min_confidence: float = 0.6
    trend_weight: float = 0.4
    momentum_weight: float = 0.3
    volume_weight: float = 0.2
    volatility_weight: float = 0.1
    ema_periods: List[int] = field(default_factory=lambda: [9, 21, 50, 200])
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9


class BiasDeterminingAgent(BaseAgent):
    """
    Determines market bias using multiple technical indicators.
    
    Responsibilities:
    - Analyze price action across multiple timeframes
    - Combine trend, momentum, volume, volatility signals
    - Output bias direction with confidence score
    - Publish bias signals for other agents
    """
    
    def __init__(self, config: AgentConfig, event_bus: EventBus = None):
        super().__init__(config, event_bus)
        
        bias_config = config.config.get("bias", {})
        self.bias_config = BiasConfig(**bias_config)
        
        # State
        self._price_history: Dict[str, Dict[str, deque]] = {}  # symbol -> timeframe -> prices
        self._volume_history: Dict[str, Dict[str, deque]] = {}
        self._current_bias: Dict[str, BiasSignal] = {}
        self._indicator_cache: Dict[str, Dict[str, Any]] = {}
        
        # Subscribe to events
        self.config.subscriptions = [
            EventType.MARKET_TICK,
            EventType.MARKET_CANDLE,
            EventType.AGENT_TUNING,
        ]
    
    async def initialize(self) -> None:
        """Initialize the agent."""
        self.status = AgentStatus.RUNNING
        await self._subscribe_to_events()
        
        await self._publish(EventType.AGENT_REGISTERED, {
            "agent": self.name,
            "capabilities": ["bias_determination", "multi_timeframe_analysis"],
            "config": self.bias_config.__dict__
        })
    
    async def start(self) -> None:
        """Start the agent."""
        self._running = True
        asyncio.create_task(self._analysis_loop())
        asyncio.create_task(self._run_heartbeat())
    
    async def stop(self) -> None:
        """Stop the agent."""
        self._running = False
        self.status = AgentStatus.STOPPED
    
    async def _handle_event(self, event: Event) -> None:
        """Handle incoming events."""
        self.update_heartbeat()
        
        if event.type == EventType.MARKET_TICK:
            await self._on_market_tick(event)
        elif event.type == EventType.MARKET_CANDLE:
            await self._on_market_candle(event)
        elif event.type == EventType.AGENT_TUNING:
            await self._on_tuning(event)
    
    async def _on_market_tick(self, event: Event) -> None:
        """Process market tick."""
        payload = event.payload
        symbol = payload.get("symbol")
        price = payload.get("price")
        volume = payload.get("volume", 0)
        timestamp = payload.get("timestamp", datetime.utcnow())
        
        if not symbol or price is None:
            return
        
        # Initialize history for symbol if needed
        if symbol not in self._price_history:
            self._price_history[symbol] = {}
            self._volume_history[symbol] = {}
            for tf in self.bias_config.timeframes:
                self._price_history[symbol][tf] = deque(maxlen=self.bias_config.lookback_periods)
                self._volume_history[symbol][tf] = deque(maxlen=self.bias_config.lookback_periods)
        
        # Ensure "1m" timeframe exists (might have been initialized by candle handler)
        if "1m" not in self._price_history[symbol]:
            self._price_history[symbol]["1m"] = deque(maxlen=self.bias_config.lookback_periods)
            self._volume_history[symbol]["1m"] = deque(maxlen=self.bias_config.lookback_periods)
        
        # Add to primary timeframe (1m base)
        self._price_history[symbol]["1m"].append({"price": price, "timestamp": timestamp, "volume": volume})
        self._volume_history[symbol]["1m"].append(volume)
    
    async def _on_market_candle(self, event: Event) -> None:
        """Process completed candle."""
        payload = event.payload
        symbol = payload.get("symbol")
        timeframe = payload.get("timeframe")
        candle = payload.get("candle", {})
        
        if not symbol or not timeframe or timeframe not in self.bias_config.timeframes:
            return
        
        # Store candle data
        if symbol not in self._price_history:
            self._price_history[symbol] = {}
            self._volume_history[symbol] = {}
        
        if timeframe not in self._price_history[symbol]:
            self._price_history[symbol][timeframe] = deque(maxlen=self.bias_config.lookback_periods)
            self._volume_history[symbol][timeframe] = deque(maxlen=self.bias_config.lookback_periods)
        
        self._price_history[symbol][timeframe].append({
            "open": candle.get("open"),
            "high": candle.get("high"),
            "low": candle.get("low"),
            "close": candle.get("close"),
            "timestamp": candle.get("timestamp", datetime.utcnow())
        })
        self._volume_history[symbol][timeframe].append(candle.get("volume", 0))
        
        # Trigger bias analysis on primary timeframe
        if timeframe == self.bias_config.primary_timeframe:
            await self._analyze_bias(symbol)
    
    async def _analyze_bias(self, symbol: str) -> None:
        """Analyze bias for a symbol across timeframes."""
        if symbol not in self._price_history:
            return
        
        # Need enough data
        primary_data = self._price_history[symbol].get(self.bias_config.primary_timeframe, [])
        if len(primary_data) < max(self.bias_config.ema_periods):
            return
        
        # Calculate indicators for each timeframe
        timeframe_signals = {}
        for tf in self.bias_config.timeframes:
            data = self._price_history[symbol].get(tf, [])
            if len(data) < 20:
                continue
            
            # Filter data that has close/high/low (skip tick-only entries)
            valid_data = [d for d in data if "close" in d and "high" in d and "low" in d]
            if len(valid_data) < 20:
                continue
            
            closes = np.array([d["close"] for d in valid_data])
            highs = np.array([d["high"] for d in valid_data])
            lows = np.array([d["low"] for d in valid_data])
            volumes = np.array(self._volume_history[symbol].get(tf, [1] * len(valid_data)))
            
            indicators = self._calculate_indicators(closes, highs, lows, volumes)
            signal = self._evaluate_timeframe_bias(indicators)
            timeframe_signals[tf] = {"indicators": indicators, "signal": signal}
        
        # Combine timeframe signals (higher timeframes weighted more)
        combined = self._combine_timeframe_signals(timeframe_signals)
        
        if combined["confidence"] >= self.bias_config.min_confidence or combined["direction"] != "neutral":
            bias_signal = BiasSignal(
                symbol=symbol,
                direction=combined["direction"],
                confidence=combined["confidence"],
                indicators=combined["indicators"],
                timestamp=datetime.utcnow(),
                timeframe=self.bias_config.primary_timeframe,
                reasoning=combined["reasoning"]
            )
            
            self._current_bias[symbol] = bias_signal
            
            # Publish bias signal
            await self._publish(EventType.BIAS_SIGNAL, {
                "symbol": symbol,
                "direction": bias_signal.direction,
                "confidence": bias_signal.confidence,
                "indicators": bias_signal.indicators,
                "timeframe": bias_signal.timeframe,
                "reasoning": bias_signal.reasoning
            })
    
    def _calculate_indicators(self, closes: np.ndarray, highs: np.ndarray, 
                             lows: np.ndarray, volumes: np.ndarray) -> Dict[str, float]:
        """Calculate technical indicators."""
        indicators = {}
        
        # EMAs
        for period in self.bias_config.ema_periods:
            if len(closes) >= period:
                ema = self._ema(closes, period)
                indicators[f"ema_{period}"] = ema[-1]
                indicators[f"ema_{period}_slope"] = ema[-1] - ema[-2] if len(ema) > 1 else 0
        
        # RSI
        if len(closes) >= self.bias_config.rsi_period:
            indicators["rsi"] = self._rsi(closes, self.bias_config.rsi_period)[-1]
        
        # MACD
        if len(closes) >= self.bias_config.macd_slow:
            macd_line, signal_line, histogram = self._macd(
                closes, self.bias_config.macd_fast, 
                self.bias_config.macd_slow, self.bias_config.macd_signal
            )
            indicators["macd"] = macd_line[-1]
            indicators["macd_signal"] = signal_line[-1]
            indicators["macd_histogram"] = histogram[-1]
        
        # Price vs EMAs
        current_price = closes[-1]
        for period in [21, 50, 200]:
            key = f"ema_{period}"
            if key in indicators:
                indicators[f"price_vs_{key}"] = (current_price - indicators[key]) / indicators[key]
        
        # Volume trend
        if len(volumes) >= 20:
            indicators["volume_sma"] = np.mean(volumes[-20:])
            indicators["volume_ratio"] = volumes[-1] / indicators["volume_sma"] if indicators["volume_sma"] > 0 else 1
        
        # Volatility (ATR proxy)
        if len(highs) >= 14 and len(lows) >= 14:
            tr = np.maximum(highs[1:] - lows[1:], 
                           np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1])))
            indicators["atr"] = np.mean(tr[-14:])
            indicators["atr_pct"] = indicators["atr"] / current_price if current_price > 0 else 0
        
        return indicators
    
    def _evaluate_timeframe_bias(self, indicators: Dict[str, float]) -> Dict[str, Any]:
        """Evaluate bias for a single timeframe."""
        bullish_score = 0.0
        bearish_score = 0.0
        reasons = []
        
        # Trend (EMA alignment)
        ema_9 = indicators.get("ema_9", 0)
        ema_21 = indicators.get("ema_21", 0)
        ema_50 = indicators.get("ema_50", 0)
        ema_200 = indicators.get("ema_200", 0)
        
        if ema_9 > ema_21 > ema_50 > ema_200:
            bullish_score += self.bias_config.trend_weight
            reasons.append("Strong uptrend (EMA alignment)")
        elif ema_9 < ema_21 < ema_50 < ema_200:
            bearish_score += self.bias_config.trend_weight
            reasons.append("Strong downtrend (EMA alignment)")
        elif ema_9 > ema_21 and ema_21 > ema_50:
            bullish_score += self.bias_config.trend_weight * 0.7
            reasons.append("Medium-term uptrend")
        elif ema_9 < ema_21 and ema_21 < ema_50:
            bearish_score += self.bias_config.trend_weight * 0.7
            reasons.append("Medium-term downtrend")
        else:
            # Partial trend: price above/below long-term EMA
            if ema_50 and ema_200 and ema_50 > ema_200:
                bullish_score += self.bias_config.trend_weight * 0.5
                reasons.append("Long-term uptrend (50 > 200)")
            elif ema_50 and ema_200 and ema_50 < ema_200:
                bearish_score += self.bias_config.trend_weight * 0.5
                reasons.append("Long-term downtrend (50 < 200)")
            elif ema_9 and ema_21 and ema_9 > ema_21:
                bullish_score += self.bias_config.trend_weight * 0.4
                reasons.append("Short-term uptrend (9 > 21)")
            elif ema_9 and ema_21 and ema_9 < ema_21:
                bearish_score += self.bias_config.trend_weight * 0.4
                reasons.append("Short-term downtrend (9 < 21)")
        
        # Price vs key EMAs
        price_vs_21 = indicators.get("price_vs_ema_21", 0)
        price_vs_50 = indicators.get("price_vs_ema_50", 0)
        
        if price_vs_21 > 0.01:
            bullish_score += 0.1
        elif price_vs_21 < -0.01:
            bearish_score += 0.1
        
        # Momentum (RSI)
        rsi = indicators.get("rsi", 50)
        if rsi > 60:
            bullish_score += self.bias_config.momentum_weight * 0.5
        elif rsi > 70:
            bullish_score += self.bias_config.momentum_weight * 0.3  # Overbought caution
            reasons.append("RSI overbought")
        elif rsi < 40:
            bearish_score += self.bias_config.momentum_weight * 0.5
        elif rsi < 30:
            bearish_score += self.bias_config.momentum_weight * 0.3  # Oversold caution
            reasons.append("RSI oversold")
        
        # MACD
        macd_hist = indicators.get("macd_histogram", 0)
        if macd_hist > 0:
            bullish_score += self.bias_config.momentum_weight * 0.5
        else:
            bearish_score += self.bias_config.momentum_weight * 0.5
        
        # Volume confirmation
        vol_ratio = indicators.get("volume_ratio", 1)
        if vol_ratio > 1.5:
            # High volume confirms direction
            if bullish_score > bearish_score:
                bullish_score += self.bias_config.volume_weight
            else:
                bearish_score += self.bias_config.volume_weight
        
        # Volatility adjustment
        atr_pct = indicators.get("atr_pct", 0)
        if atr_pct > 0.05:  # High volatility
            # Reduce confidence in both directions
            bullish_score *= 0.8
            bearish_score *= 0.8
            reasons.append("High volatility reducing confidence")
        
        # Determine direction
        if bullish_score > bearish_score:
            direction = "bullish"
            confidence = min(bullish_score, 1.0)
        elif bearish_score > bullish_score:
            direction = "bearish"
            confidence = min(bearish_score, 1.0)
        else:
            direction = "neutral"
            confidence = 0.5
        
        return {
            "direction": direction,
            "confidence": confidence,
            "bullish_score": bullish_score,
            "bearish_score": bearish_score,
            "reasons": reasons
        }
    
    def _combine_timeframe_signals(self, signals: Dict[str, Dict]) -> Dict[str, Any]:
        """Combine signals from multiple timeframes with weights."""
        # Higher timeframes get more weight
        tf_weights = {
            "1m": 0.05, "5m": 0.1, "15m": 0.2, "1h": 0.3, "4h": 0.35
        }
        
        total_bullish = 0.0
        total_bearish = 0.0
        total_weight = 0.0
        all_reasons = []
        combined_indicators = {}
        
        for tf, data in signals.items():
            weight = tf_weights.get(tf, 0.1)
            signal = data["signal"]
            
            total_bullish += signal["bullish_score"] * weight
            total_bearish += signal["bearish_score"] * weight
            total_weight += weight
            all_reasons.extend([f"[{tf}] {r}" for r in signal["reasons"]])
            
            # Merge indicators with timeframe prefix
            for k, v in data["indicators"].items():
                combined_indicators[f"{tf}_{k}"] = v
        
        if total_weight == 0:
            return {"direction": "neutral", "confidence": 0.5, "indicators": {}, "reasoning": "Insufficient data"}
        
        bullish_norm = total_bullish / total_weight
        bearish_norm = total_bearish / total_weight
        
        if bullish_norm > bearish_norm:
            direction = "bullish"
            confidence = min(bullish_norm, 1.0)
        elif bearish_norm > bullish_norm:
            direction = "bearish"
            confidence = min(bearish_norm, 1.0)
        else:
            direction = "neutral"
            confidence = 0.5
        
        return {
            "direction": direction,
            "confidence": confidence,
            "indicators": combined_indicators,
            "reasoning": "; ".join(all_reasons) if all_reasons else "Mixed signals"
        }
    
    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Exponential Moving Average."""
        alpha = 2 / (period + 1)
        ema = np.zeros_like(data)
        ema[0] = data[0]
        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i-1]
        return ema
    
    def _rsi(self, data: np.ndarray, period: int) -> np.ndarray:
        """Relative Strength Index."""
        deltas = np.diff(data)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.zeros_like(data)
        avg_loss = np.zeros_like(data)
        avg_gain[period] = np.mean(gains[:period])
        avg_loss[period] = np.mean(losses[:period])
        
        for i in range(period + 1, len(data)):
            avg_gain[i] = (avg_gain[i-1] * (period - 1) + gains[i-1]) / period
            avg_loss[i] = (avg_loss[i-1] * (period - 1) + losses[i-1]) / period
        
        rs = np.where(avg_loss > 0, avg_gain / avg_loss, 100)
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _macd(self, data: np.ndarray, fast: int, slow: int, signal: int) -> tuple:
        """MACD indicator."""
        ema_fast = self._ema(data, fast)
        ema_slow = self._ema(data, slow)
        macd_line = ema_fast - ema_slow
        signal_line = self._ema(macd_line, signal)
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram
    
    async def _on_tuning(self, event: Event) -> None:
        """Handle tuning from ManagerAgent."""
        payload = event.payload
        if payload.get("target_agent") == self.name:
            params = payload.get("parameters", {})
            for key, value in params.items():
                if hasattr(self.bias_config, key):
                    setattr(self.bias_config, key, value)
    
    async def _analysis_loop(self) -> None:
        """Periodic bias re-analysis."""
        while self._running:
            await asyncio.sleep(30)  # Re-analyze every 30 seconds
            
            for symbol in list(self._price_history.keys()):
                await self._analyze_bias(symbol)
            
            # Publish current biases
            await self._publish(EventType.AGENT_HEARTBEAT, {
                "agent": self.name,
                "status": self.status.value,
                "biases": {s: {"direction": b.direction, "confidence": b.confidence} 
                          for s, b in self._current_bias.items()}
            })