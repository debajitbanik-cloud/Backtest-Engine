"""
Multi-Timeframe Confluence Agent
Checks for confluence across multiple timeframes before allowing trades.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List, Literal
from collections import deque
import numpy as np

from core.base_agent import BaseAgent, AgentConfig, AgentStatus
from core.event_bus import EventBus, Event, EventType, event_bus


ConfluenceResult = Literal["strong_bullish", "bullish", "neutral", "bearish", "strong_bearish"]


@dataclass
class ConfluenceSignal:
    """Confluence analysis result."""
    symbol: str
    result: ConfluenceResult
    confidence: float
    timeframe_alignments: Dict[str, str]  # timeframe -> bias
    key_levels: Dict[str, float]
    timestamp: datetime
    reasoning: str


@dataclass
class ConfluenceConfig:
    """Configuration for confluence checking."""
    timeframes: List[str] = field(default_factory=lambda: ["5m", "15m", "1h", "4h", "1d"])
    required_alignment: int = 3  # Minimum timeframes aligned
    strong_alignment: int = 4  # Timeframes for strong signal
    lookback_candles: int = 100
    key_level_lookback: int = 50
    min_confidence: float = 0.65
    sr_touch_threshold: float = 0.002  # 0.2% from level
    volume_confirmation: bool = True


class MultiTimeframeConfluenceAgent(BaseAgent):
    """
    Checks for confluence across multiple timeframes.
    
    Responsibilities:
    - Analyze trend alignment across timeframes
    - Identify key support/resistance levels
    - Detect confluence zones (multiple factors aligning)
    - Filter trade signals based on confluence
    - Publish confluence signals for PositionSizingAgent
    """
    
    def __init__(self, config: AgentConfig, event_bus: EventBus = None):
        super().__init__(config, event_bus)
        
        confluence_config = config.config.get("confluence", {})
        self.confluence_config = ConfluenceConfig(**confluence_config)
        
        # State
        self._candle_data: Dict[str, Dict[str, deque]] = {}  # symbol -> timeframe -> candles
        self._key_levels: Dict[str, Dict[str, List[float]]] = {}  # symbol -> timeframe -> levels
        self._last_confluence: Dict[str, ConfluenceSignal] = {}
        self._pending_bias_signals: Dict[str, Dict] = {}  # Store bias signals for combination
        
        # Subscribe to events
        self.config.subscriptions = [
            EventType.MARKET_CANDLE,
            EventType.BIAS_SIGNAL,
            EventType.AGENT_TUNING,
        ]
    
    async def initialize(self) -> None:
        """Initialize the agent."""
        self.status = AgentStatus.RUNNING
        await self._subscribe_to_events()
        
        await self._publish(EventType.AGENT_REGISTERED, {
            "agent": self.name,
            "capabilities": ["multi_timeframe_confluence", "support_resistance", "signal_filtering"],
            "config": self.confluence_config.__dict__
        })
    
    async def start(self) -> None:
        """Start the agent."""
        self._running = True
        asyncio.create_task(self._confluence_loop())
        asyncio.create_task(self._run_heartbeat())
    
    async def stop(self) -> None:
        """Stop the agent."""
        self._running = False
        self.status = AgentStatus.STOPPED
    
    async def _handle_event(self, event: Event) -> None:
        """Handle incoming events."""
        self.update_heartbeat()
        
        if event.type == EventType.MARKET_CANDLE:
            await self._on_market_candle(event)
        elif event.type == EventType.BIAS_SIGNAL:
            await self._on_bias_signal(event)
        elif event.type == EventType.AGENT_TUNING:
            await self._on_tuning(event)
    
    async def _on_market_candle(self, event: Event) -> None:
        """Store candle data for analysis."""
        payload = event.payload
        symbol = payload.get("symbol")
        timeframe = payload.get("timeframe")
        candle = payload.get("candle", {})
        
        if not symbol or not timeframe or timeframe not in self.confluence_config.timeframes:
            return
        
        if symbol not in self._candle_data:
            self._candle_data[symbol] = {}
            self._key_levels[symbol] = {}
        
        if timeframe not in self._candle_data[symbol]:
            self._candle_data[symbol][timeframe] = deque(maxlen=self.confluence_config.lookback_candles)
            self._key_levels[symbol][timeframe] = []
        
        self._candle_data[symbol][timeframe].append({
            "open": candle.get("open"),
            "high": candle.get("high"),
            "low": candle.get("low"),
            "close": candle.get("close"),
            "volume": candle.get("volume", 0),
            "timestamp": candle.get("timestamp", datetime.utcnow())
        })
        
        # Update key levels periodically
        if len(self._candle_data[symbol][timeframe]) % 20 == 0:
            await self._update_key_levels(symbol, timeframe)
    
    async def _on_bias_signal(self, event: Event) -> None:
        """Store bias signals from BiasDeterminingAgent."""
        payload = event.payload
        symbol = payload.get("symbol")
        direction = payload.get("direction")
        confidence = payload.get("confidence")
        timeframe = payload.get("timeframe")
        
        if not symbol:
            return
        
        if symbol not in self._pending_bias_signals:
            self._pending_bias_signals[symbol] = {}
        
        self._pending_bias_signals[symbol][timeframe] = {
            "direction": direction,
            "confidence": confidence,
            "timestamp": datetime.utcnow()
        }
        
        # Check if we have enough timeframes to evaluate confluence
        if len(self._pending_bias_signals[symbol]) >= self.confluence_config.required_alignment:
            await self._evaluate_confluence(symbol)
    
    async def _update_key_levels(self, symbol: str, timeframe: str) -> None:
        """Calculate support/resistance levels for a timeframe."""
        candles = self._candle_data[symbol].get(timeframe, [])
        if len(candles) < 20:
            return
        
        highs = np.array([c["high"] for c in candles])
        lows = np.array([c["low"] for c in candles])
        closes = np.array([c["close"] for c in candles])
        
        # Find swing highs/lows
        swing_highs = []
        swing_lows = []
        
        for i in range(2, len(candles) - 2):
            # Swing high
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                swing_highs.append(highs[i])
            # Swing low
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                swing_lows.append(lows[i])
        
        # Cluster nearby levels
        all_levels = swing_highs + swing_lows
        if not all_levels:
            return
        
        clustered = self._cluster_levels(all_levels, threshold_pct=0.005)
        
        # Keep strongest levels (tested multiple times)
        current_price = closes[-1]
        tested_levels = []
        for level in clustered:
            touches = sum(1 for c in candles if abs(c["high"] - level) / level < self.confluence_config.sr_touch_threshold 
                         or abs(c["low"] - level) / level < self.confluence_config.sr_touch_threshold)
            if touches >= 2:
                tested_levels.append((level, touches))
        
        # Sort by touch count and proximity to current price
        tested_levels.sort(key=lambda x: (-x[1], abs(x[0] - current_price)))
        self._key_levels[symbol][timeframe] = [l[0] for l in tested_levels[:10]]
    
    def _cluster_levels(self, levels: List[float], threshold_pct: float = 0.005) -> List[float]:
        """Cluster nearby price levels."""
        if not levels:
            return []
        
        sorted_levels = sorted(levels)
        clusters = []
        current_cluster = [sorted_levels[0]]
        
        for level in sorted_levels[1:]:
            if abs(level - current_cluster[-1]) / current_cluster[-1] < threshold_pct:
                current_cluster.append(level)
            else:
                clusters.append(np.mean(current_cluster))
                current_cluster = [level]
        
        clusters.append(np.mean(current_cluster))
        return clusters
    
    async def _evaluate_confluence(self, symbol: str) -> None:
        """Evaluate confluence across timeframes."""
        biases = self._pending_bias_signals.get(symbol, {})
        candles = self._candle_data.get(symbol, {})
        
        if not biases or not candles:
            return
        
        # Count alignments
        bullish_count = sum(1 for v in biases.values() if v["direction"] == "bullish")
        bearish_count = sum(1 for v in biases.values() if v["direction"] == "bearish")
        neutral_count = sum(1 for v in biases.values() if v["direction"] == "neutral")
        total_count = len(biases)
        
        # Get timeframe alignments
        alignments = {tf: v["direction"] for tf, v in biases.items()}
        
        # Check key level confluence
        current_price = None
        for tf in self.confluence_config.timeframes:
            tf_candles = candles.get(tf, [])
            if tf_candles:
                current_price = tf_candles[-1]["close"]
                break
        
        key_levels = {}
        level_confluence = 0
        if current_price:
            for tf in self.confluence_config.timeframes:
                levels = self._key_levels.get(symbol, {}).get(tf, [])
                for level in levels:
                    dist_pct = abs(current_price - level) / current_price
                    if dist_pct < self.confluence_config.sr_touch_threshold:
                        key_levels[f"{tf}_level"] = level
                        level_confluence += 1
        
        # Determine confluence result
        confidence = 0.0
        reasoning_parts = []
        
        if bullish_count >= self.confluence_config.strong_alignment:
            result = "strong_bullish"
            confidence = 0.9
            reasoning_parts.append(f"{bullish_count}/{total_count} timeframes strongly bullish")
        elif bullish_count >= self.confluence_config.required_alignment:
            result = "bullish"
            confidence = 0.7 + (bullish_count / total_count) * 0.2
            reasoning_parts.append(f"{bullish_count}/{total_count} timeframes bullish")
        elif bearish_count >= self.confluence_config.strong_alignment:
            result = "strong_bearish"
            confidence = 0.9
            reasoning_parts.append(f"{bearish_count}/{total_count} timeframes strongly bearish")
        elif bearish_count >= self.confluence_config.required_alignment:
            result = "bearish"
            confidence = 0.7 + (bearish_count / total_count) * 0.2
            reasoning_parts.append(f"{bearish_count}/{total_count} timeframes bearish")
        else:
            result = "neutral"
            confidence = 0.5
            reasoning_parts.append(f"No clear alignment: {bullish_count} bullish, {bearish_count} bearish, {neutral_count} neutral")
        
        # Boost confidence with key level confluence
        if level_confluence >= 2:
            confidence = min(confidence + 0.1 * level_confluence, 1.0)
            reasoning_parts.append(f"{level_confluence} key levels confluent")
        
        # Volume confirmation
        if self.confluence_config.volume_confirmation:
            vol_confirmed = self._check_volume_confirmation(symbol, biases)
            if vol_confirmed:
                confidence = min(confidence + 0.05, 1.0)
                reasoning_parts.append("Volume confirms")
            else:
                confidence *= 0.9
                reasoning_parts.append("Volume divergence")
        
        if confidence < self.confluence_config.min_confidence:
            result = "neutral"
            confidence = max(confidence, 0.5)
        
        confluence_signal = ConfluenceSignal(
            symbol=symbol,
            result=result,
            confidence=confidence,
            timeframe_alignments=alignments,
            key_levels=key_levels,
            timestamp=datetime.utcnow(),
            reasoning="; ".join(reasoning_parts)
        )
        
        self._last_confluence[symbol] = confluence_signal
        
        # Clear processed bias signals
        self._pending_bias_signals[symbol] = {}
        
        # Publish confluence signal
        await self._publish(EventType.CONFLUENCE_SIGNAL, {
            "symbol": symbol,
            "result": result,
            "confidence": confidence,
            "alignments": alignments,
            "key_levels": key_levels,
            "reasoning": confluence_signal.reasoning
        })
    
    def _check_volume_confirmation(self, symbol: str, biases: Dict) -> bool:
        """Check if volume confirms the bias direction."""
        # Simplified: check if recent volume is above average on aligned timeframes
        for tf, bias in biases.items():
            candles = self._candle_data.get(symbol, {}).get(tf, [])
            if len(candles) < 20:
                continue
            
            volumes = [c["volume"] for c in list(candles)[-20:]]
            avg_vol = np.mean(volumes[:-1])
            recent_vol = volumes[-1]
            
            if recent_vol > avg_vol * 1.2:
                return True
        return False
    
    async def _on_tuning(self, event: Event) -> None:
        """Handle tuning from ManagerAgent."""
        payload = event.payload
        if payload.get("target_agent") == self.name:
            params = payload.get("parameters", {})
            for key, value in params.items():
                if hasattr(self.confluence_config, key):
                    setattr(self.confluence_config, key, value)
    
    async def _confluence_loop(self) -> None:
        """Periodic confluence re-evaluation."""
        while self._running:
            await asyncio.sleep(60)  # Check every minute
            
            for symbol in list(self._candle_data.keys()):
                # Re-evaluate if we have fresh bias signals
                if symbol in self._pending_bias_signals and self._pending_bias_signals[symbol]:
                    await self._evaluate_confluence(symbol)
            
            await self._publish(EventType.AGENT_HEARTBEAT, {
                "agent": self.name,
                "status": self.status.value,
                "confluences": {s: {"result": c.result, "confidence": c.confidence} 
                               for s, c in self._last_confluence.items()}
            })