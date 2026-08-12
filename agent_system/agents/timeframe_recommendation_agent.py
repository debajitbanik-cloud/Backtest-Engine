"""
Timeframe Recommendation Agent
===============================
Major timeframe adjusting filter that aggregates all agent signals
into a single actionable recommendation.

Consumes:
- BiasDeterminingAgent → BIAS_SIGNAL
- MultiTimeframeConfluenceAgent → CONFLUENCE_SIGNAL
- StyleManagingAgent → MODE_SWITCH
- RiskCheckingAgent → RISK_ALERT
- LeverageAdjustmentAgent → LEVERAGE_ADJUSTMENT
- XAU AI integration → optional SMC/regime signals

Produces:
- TIMEFRAME_RECOMMENDATION with:
  - Recommended timeframe (1m/5m/15m/1h/4h)
  - Direction (long/short/flat)
  - Confidence (0-1)
  - Confluence score
  - Reasoning across all sources
  - Alignment matrix
"""

from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
from collections import deque

from core.base_agent import BaseAgent, AgentConfig, AgentStatus
from core.event_bus import EventBus, Event, EventType, event_bus


@dataclass
class TimeframeRecommendation:
    """Unified recommendation across all agents."""
    symbol: str
    recommended_timeframe: str
    direction: str  # long / short / flat
    confidence: float  # 0-1
    confluence_score: float
    bias_score: float
    risk_score: float
    alignment: Dict[str, str]  # agent -> signal
    reasoning: List[str]
    timestamp: datetime


@dataclass
class RecommendationConfig:
    """Configuration for recommendation aggregation."""
    available_timeframes: List[str] = field(default_factory=lambda: ["1m", "5m", "15m", "1h", "4h"])
    preferred_timeframes: List[str] = field(default_factory=lambda: ["15m", "1h"])
    min_confidence: float = 0.55
    confluence_weight: float = 0.35
    bias_weight: float = 0.30
    risk_weight: float = 0.20
    mode_weight: float = 0.15
    max_history: int = 100


class TimeframeRecommendationAgent(BaseAgent):
    """
    Aggregates signals from all agents into a single recommendation.
    
    This is the "major timeframe adjusting filter" that:
    1. Listens to all upstream agents
    2. Scores each timeframe based on agent alignment
    3. Recommends the best timeframe + direction
    4. Publishes TIMEFRAME_RECOMMENDATION for downstream use
    """
    
    def __init__(self, config: AgentConfig, event_bus: EventBus = None):
        super().__init__(config, event_bus)
        
        rec_config = config.config.get("recommendation", {})
        self.rec_config = RecommendationConfig(**rec_config)
        
        # Signal state
        self._bias_signals: Dict[str, Dict] = {}
        self._confluence_signals: Dict[str, Dict] = {}
        self._mode_signals: Dict[str, Dict] = {}
        self._risk_signals: Dict[str, Dict] = {}
        self._leverage_signals: Dict[str, Dict] = {}
        
        # Latest recommendation per symbol
        self._recommendations: Dict[str, TimeframeRecommendation] = {}
        self._history: Dict[str, deque] = {}
        
        # Subscribe to upstream events
        self.config.subscriptions = [
            EventType.BIAS_SIGNAL,
            EventType.CONFLUENCE_SIGNAL,
            EventType.MODE_SWITCH,
            EventType.RISK_ALERT,
            EventType.LEVERAGE_ADJUSTMENT,
            EventType.AGENT_TUNING,
        ]
    
    async def initialize(self) -> None:
        """Initialize the agent."""
        self.status = AgentStatus.RUNNING
        await self._subscribe_to_events()
        
        await self._publish(EventType.AGENT_REGISTERED, {
            "agent": self.name,
            "capabilities": ["timeframe_recommendation", "signal_aggregation", "confluence_filter"],
            "config": self.rec_config.__dict__
        })
    
    async def start(self) -> None:
        """Start the agent."""
        self._running = True
        asyncio.create_task(self._recommendation_loop())
        asyncio.create_task(self._run_heartbeat())
    
    async def stop(self) -> None:
        """Stop the agent."""
        self._running = False
        self.status = AgentStatus.STOPPED
    
    async def _handle_event(self, event: Event) -> None:
        """Handle incoming events."""
        self.update_heartbeat()
        
        if event.type == EventType.BIAS_SIGNAL:
            await self._on_bias(event)
        elif event.type == EventType.CONFLUENCE_SIGNAL:
            await self._on_confluence(event)
        elif event.type == EventType.MODE_SWITCH:
            await self._on_mode(event)
        elif event.type == EventType.RISK_ALERT:
            await self._on_risk(event)
        elif event.type == EventType.LEVERAGE_ADJUSTMENT:
            await self._on_leverage(event)
        elif event.type == EventType.AGENT_TUNING:
            await self._on_tuning(event)
    
    async def _on_bias(self, event: Event) -> None:
        payload = event.payload
        symbol = payload.get("symbol")
        if not symbol:
            return
        
        self._bias_signals[symbol] = {
            "direction": payload.get("direction", "neutral"),
            "confidence": payload.get("confidence", 0.5),
            "timeframe": payload.get("timeframe", "15m"),
            "indicators": payload.get("indicators", {}),
            "timestamp": datetime.utcnow(),
        }
        
        await self._maybe_recommend(symbol)
    
    async def _on_confluence(self, event: Event) -> None:
        payload = event.payload
        symbol = payload.get("symbol")
        if not symbol:
            return
        
        self._confluence_signals[symbol] = {
            "result": payload.get("result", "neutral"),
            "confidence": payload.get("confidence", 0.5),
            "alignments": payload.get("alignments", {}),
            "key_levels": payload.get("key_levels", {}),
            "timestamp": datetime.utcnow(),
        }
        
        await self._maybe_recommend(symbol)
    
    async def _on_mode(self, event: Event) -> None:
        payload = event.payload
        new_mode = payload.get("new_mode", "swing")
        
        # Mode signals are global, apply to all known symbols
        for symbol in self._bias_signals.keys():
            self._mode_signals[symbol] = {
                "mode": new_mode,
                "reasoning": payload.get("reasoning", ""),
                "parameters": payload.get("parameters", {}),
                "timestamp": datetime.utcnow(),
            }
            await self._maybe_recommend(symbol)
    
    async def _on_risk(self, event: Event) -> None:
        payload = event.payload
        symbol = payload.get("symbol")
        if not symbol:
            return
        
        self._risk_signals[symbol] = {
            "risk_level": payload.get("risk_level", "low"),
            "action": payload.get("action", "none"),
            "reasoning": payload.get("reasoning", ""),
            "timestamp": datetime.utcnow(),
        }
        
        await self._maybe_recommend(symbol)
    
    async def _on_leverage(self, event: Event) -> None:
        payload = event.payload
        symbol = payload.get("symbol")
        if not symbol:
            return
        
        self._leverage_signals[symbol] = {
            "leverage": payload.get("leverage", 10),
            "action": payload.get("action", "none"),
            "timestamp": datetime.utcnow(),
        }
    
    async def _on_tuning(self, event: Event) -> None:
        payload = event.payload
        if payload.get("target_agent") == self.name:
            params = payload.get("parameters", {})
            for key, value in params.items():
                if hasattr(self.rec_config, key):
                    setattr(self.rec_config, key, value)
    
    async def _maybe_recommend(self, symbol: str) -> None:
        """Generate recommendation if enough signals available."""
        bias = self._bias_signals.get(symbol)
        confluence = self._confluence_signals.get(symbol)
        mode = self._mode_signals.get(symbol)
        
        # Require at least bias signal; confluence optional
        if not bias:
            return
        
        recommendation = await self._generate_recommendation(symbol, bias, confluence, mode)
        self._recommendations[symbol] = recommendation
        
        # Store in history
        if symbol not in self._history:
            self._history[symbol] = deque(maxlen=self.rec_config.max_history)
        self._history[symbol].append(recommendation)
        
        # Publish
        await self._publish(EventType.TIMEFRAME_RECOMMENDATION, {
            "symbol": symbol,
            "recommended_timeframe": recommendation.recommended_timeframe,
            "direction": recommendation.direction,
            "confidence": recommendation.confidence,
            "confluence_score": recommendation.confluence_score,
            "bias_score": recommendation.bias_score,
            "risk_score": recommendation.risk_score,
            "alignment": recommendation.alignment,
            "reasoning": recommendation.reasoning,
            "timestamp": recommendation.timestamp.isoformat(),
        })
    
    async def _generate_recommendation(
        self, symbol: str, bias: Dict, confluence: Optional[Dict], mode: Optional[Dict]
    ) -> TimeframeRecommendation:
        """Generate unified recommendation from all signals."""
        reasoning = []
        alignment = {}
        
        # 1. Bias score (0-1)
        bias_direction = bias.get("direction", "neutral")
        bias_conf = bias.get("confidence", 0.5)
        bias_score = bias_conf if bias_direction in ("bullish", "bearish") else 0.3
        
        # 2. Confluence score (optional)
        if confluence:
            confluence_result = confluence.get("result", "neutral")
            confluence_conf = confluence.get("confidence", 0.5)
            
            if confluence_result == "strong_bullish":
                confluence_score = confluence_conf
                confluence_dir = "long"
            elif confluence_result == "bullish":
                confluence_score = confluence_conf * 0.8
                confluence_dir = "long"
            elif confluence_result == "strong_bearish":
                confluence_score = confluence_conf
                confluence_dir = "short"
            elif confluence_result == "bearish":
                confluence_score = confluence_conf * 0.8
                confluence_dir = "short"
            else:
                confluence_score = 0.3
                confluence_dir = "flat"
        else:
            # No confluence signal: derive from bias
            confluence_score = bias_score * 0.7
            confluence_dir = "long" if bias_direction == "bullish" else "short" if bias_direction == "bearish" else "flat"
            confluence_result = "unavailable"
        
        # 3. Mode score
        if mode:
            mode_name = mode.get("mode", "swing")
            if mode_name == "scalping":
                mode_score = 0.7
                mode_timeframe = "5m"
            elif mode_name == "swing":
                mode_score = 0.8
                mode_timeframe = "1h"
            else:
                mode_score = 0.6
                mode_timeframe = "15m"
        else:
            mode_score = 0.5
            mode_timeframe = "15m"
        
        # 4. Risk score
        risk = self._risk_signals.get(symbol, {})
        risk_level = risk.get("risk_level", "low")
        if risk_level == "low":
            risk_score = 0.9
        elif risk_level == "medium":
            risk_score = 0.6
        elif risk_level == "high":
            risk_score = 0.4
        else:
            risk_score = 0.2
        
        # 5. Determine direction
        if confluence_dir == "long" and bias_direction == "bullish":
            direction = "long"
        elif confluence_dir == "short" and bias_direction == "bearish":
            direction = "short"
        elif confluence_dir == "flat" or bias_direction == "neutral":
            direction = "flat"
        else:
            # Conflicting signals
            if confluence_score > bias_score:
                direction = confluence_dir
            elif bias_score > confluence_score:
                direction = "long" if bias_direction == "bullish" else "short"
            else:
                direction = "flat"
        
        # 6. Select recommended timeframe
        # Higher confluence + mode timeframe = recommendation
        tf_score = {}
        confluence_alignments = (confluence or {}).get("alignments", {})
        for tf in self.rec_config.available_timeframes:
            score = 0.0
            if tf == mode_timeframe:
                score += 0.4
            if tf in self.rec_config.preferred_timeframes:
                score += 0.3
            if tf == "15m":
                score += 0.15  # Default preference
            if tf in confluence_alignments:
                score += 0.15
            tf_score[tf] = score
        
        recommended_tf = max(tf_score, key=tf_score.get)
        
        # 7. Combined confidence
        confidence = (
            self.rec_config.bias_weight * bias_score +
            self.rec_config.confluence_weight * confluence_score +
            self.rec_config.mode_weight * mode_score +
            self.rec_config.risk_weight * risk_score
        )
        
        if confidence < self.rec_config.min_confidence and direction != "flat":
            direction = "flat"
        
        # Build reasoning
        reasoning.append(f"Bias: {bias_direction} ({bias_conf:.2f})")
        if confluence:
            reasoning.append(f"Confluence: {confluence_result} ({confluence_conf:.2f})")
        else:
            reasoning.append("Confluence: not yet available")
        if mode:
            reasoning.append(f"Mode: {mode.get('mode', 'swing')}")
        reasoning.append(f"Risk: {risk_level}")
        reasoning.append(f"Recommended timeframe: {recommended_tf}")
        
        # Alignment matrix
        alignment = {
            "bias_agent": bias_direction,
            "confluence_agent": confluence_result,
            "style_agent": mode.get("mode", "unknown") if mode else "unknown",
            "risk_agent": risk_level,
        }
        
        return TimeframeRecommendation(
            symbol=symbol,
            recommended_timeframe=recommended_tf,
            direction=direction,
            confidence=min(confidence, 1.0),
            confluence_score=confluence_score,
            bias_score=bias_score,
            risk_score=risk_score,
            alignment=alignment,
            reasoning=reasoning,
            timestamp=datetime.utcnow(),
        )
    
    async def _recommendation_loop(self) -> None:
        """Periodic recommendation refresh."""
        while self._running:
            await asyncio.sleep(30)
            
            for symbol in list(self._bias_signals.keys()):
                await self._maybe_recommend(symbol)
            
            # Heartbeat
            await self._publish(EventType.AGENT_HEARTBEAT, {
                "agent": self.name,
                "status": self.status.value,
                "recommendations": {
                    s: {
                        "timeframe": r.recommended_timeframe,
                        "direction": r.direction,
                        "confidence": r.confidence,
                    }
                    for s, r in self._recommendations.items()
                }
            })
    
    def get_recommendation(self, symbol: str) -> Optional[Dict]:
        """Get latest recommendation for a symbol."""
        rec = self._recommendations.get(symbol)
        if not rec:
            return None
        
        return {
            "symbol": rec.symbol,
            "recommended_timeframe": rec.recommended_timeframe,
            "direction": rec.direction,
            "confidence": rec.confidence,
            "confluence_score": rec.confluence_score,
            "bias_score": rec.bias_score,
            "risk_score": rec.risk_score,
            "alignment": rec.alignment,
            "reasoning": rec.reasoning,
            "timestamp": rec.timestamp.isoformat(),
        }
    
    def get_all_recommendations(self) -> Dict[str, Dict]:
        """Get all latest recommendations."""
        return {s: self.get_recommendation(s) for s in self._recommendations}
