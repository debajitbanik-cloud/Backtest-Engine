"""
Style Managing Agent
Switches between scalping and swing trading modes based on market conditions.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Literal
from enum import Enum
from collections import deque

from core.base_agent import BaseAgent, AgentConfig, AgentStatus
from core.event_bus import EventBus, Event, EventType, event_bus


class TradingMode(Enum):
    """Trading style modes."""
    SCALPING = "scalping"       # 15m max hold, high frequency
    SWING = "swing"             # 1%+ target, hours to days
    HYBRID = "hybrid"           # Both simultaneously


@dataclass
class ModeConfig:
    """Configuration for each trading mode."""
    # Scalping config
    scalping_max_hold_minutes: int = 15
    scalping_target_pct: float = 0.003  # 0.3%
    scalping_stop_pct: float = 0.002    # 0.2%
    scalping_min_volatility: float = 0.005  # 0.5% ATR
    scalping_max_spread_pct: float = 0.001  # 0.1%
    
    # Swing config
    swing_target_pct: float = 0.01      # 1%+
    swing_stop_pct: float = 0.005       # 0.5%
    swing_min_hold_hours: int = 2
    swing_max_hold_days: int = 7
    swing_min_trend_strength: float = 0.6
    
    # Switching criteria
    volatility_threshold_high: float = 0.03   # High vol -> scalping
    volatility_threshold_low: float = 0.01    # Low vol -> swing
    trend_threshold: float = 0.65             # Strong trend -> swing
    volume_threshold: float = 1.5             # High volume -> scalping
    cooldown_hours: int = 1                   # Min time between switches


@dataclass
class ModeSignal:
    """Trading mode recommendation."""
    mode: TradingMode
    confidence: float
    reasoning: str
    parameters: Dict[str, Any]
    timestamp: datetime


class StyleManagingAgent(BaseAgent):
    """
    Manages trading style (scalping vs swing) based on market conditions.
    
    Responsibilities:
    - Monitor market volatility, trend strength, volume
    - Switch between scalping and swing modes
    - Provide mode-specific parameters to other agents
    - Track mode performance for optimization
    """
    
    def __init__(self, config: AgentConfig, event_bus: EventBus = None):
        super().__init__(config, event_bus)
        
        style_config = config.config.get("style", {})
        self.style_config = ModeConfig(**style_config)
        
        # State
        self._current_mode: TradingMode = TradingMode.SWING
        self._mode_history: List[Dict] = []
        self._last_switch: Optional[datetime] = None
        self._market_metrics: Dict[str, Dict] = {}  # symbol -> metrics
        self._mode_performance: Dict[TradingMode, Dict] = {
            TradingMode.SCALPING: {"trades": 0, "wins": 0, "total_pnl": 0.0},
            TradingMode.SWING: {"trades": 0, "wins": 0, "total_pnl": 0.0},
        }
        
        # Subscribe to events
        self.config.subscriptions = [
            EventType.MARKET_TICK,
            EventType.MARKET_CANDLE,
            EventType.BIAS_SIGNAL,
            EventType.CONFLUENCE_SIGNAL,
            EventType.TRADE_EXECUTED,
            EventType.AGENT_TUNING,
        ]
    
    async def initialize(self) -> None:
        """Initialize the agent."""
        self.status = AgentStatus.RUNNING
        await self._subscribe_to_events()
        
        await self._publish(EventType.AGENT_REGISTERED, {
            "agent": self.name,
            "capabilities": ["style_management", "mode_switching", "parameter_optimization"],
            "current_mode": self._current_mode.value,
            "config": self.style_config.__dict__
        })
    
    async def start(self) -> None:
        """Start the agent."""
        self._running = True
        asyncio.create_task(self._mode_evaluation_loop())
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
        elif event.type == EventType.BIAS_SIGNAL:
            await self._on_bias_signal(event)
        elif event.type == EventType.CONFLUENCE_SIGNAL:
            await self._on_confluence_signal(event)
        elif event.type == EventType.TRADE_EXECUTED:
            await self._on_trade_executed(event)
        elif event.type == EventType.AGENT_TUNING:
            await self._on_tuning(event)
    
    async def _on_market_tick(self, event: Event) -> None:
        """Update real-time metrics."""
        payload = event.payload
        symbol = payload.get("symbol")
        price = payload.get("price")
        volume = payload.get("volume", 0)
        
        if not symbol or price is None:
            return
        
        if symbol not in self._market_metrics:
            self._market_metrics[symbol] = {
                "prices": deque(maxlen=100),
                "volumes": deque(maxlen=100),
                "returns": deque(maxlen=100),
                "last_price": price
            }
        
        metrics = self._market_metrics[symbol]
        if metrics["prices"]:
            ret = (price - metrics["last_price"]) / metrics["last_price"]
            metrics["returns"].append(ret)
        metrics["prices"].append(price)
        metrics["volumes"].append(volume)
        metrics["last_price"] = price
    
    async def _on_market_candle(self, event: Event) -> None:
        """Process completed candles for metrics."""
        payload = event.payload
        symbol = payload.get("symbol")
        timeframe = payload.get("timeframe")
        candle = payload.get("candle", {})
        
        if not symbol or timeframe != "15m":  # Use 15m for mode decisions
            return
        
        if symbol not in self._market_metrics:
            self._market_metrics[symbol] = {"candles": deque(maxlen=100)}
        elif "candles" not in self._market_metrics[symbol]:
            self._market_metrics[symbol]["candles"] = deque(maxlen=100)
        
        self._market_metrics[symbol]["candles"].append(candle)
    
    async def _on_bias_signal(self, event: Event) -> None:
        """Track bias for trend strength."""
        payload = event.payload
        symbol = payload.get("symbol")
        confidence = payload.get("confidence", 0)
        direction = payload.get("direction")
        
        if symbol and symbol in self._market_metrics:
            self._market_metrics[symbol]["bias_confidence"] = confidence
            self._market_metrics[symbol]["bias_direction"] = direction
    
    async def _on_confluence_signal(self, event: Event) -> None:
        """Track confluence for mode decisions."""
        payload = event.payload
        symbol = payload.get("symbol")
        result = payload.get("result")
        confidence = payload.get("confidence", 0)
        
        if symbol and symbol in self._market_metrics:
            self._market_metrics[symbol]["confluence_result"] = result
            self._market_metrics[symbol]["confluence_confidence"] = confidence
    
    async def _on_trade_executed(self, event: Event) -> None:
        """Track trade performance by mode."""
        payload = event.payload
        mode = payload.get("mode", self._current_mode.value)
        pnl = payload.get("pnl", 0)
        
        try:
            trade_mode = TradingMode(mode)
            perf = self._mode_performance[trade_mode]
            perf["trades"] += 1
            if pnl > 0:
                perf["wins"] += 1
            perf["total_pnl"] += pnl
        except ValueError:
            pass
    
    async def _on_tuning(self, event: Event) -> None:
        """Handle tuning from ManagerAgent."""
        payload = event.payload
        if payload.get("target_agent") == self.name:
            params = payload.get("parameters", {})
            for key, value in params.items():
                if hasattr(self.style_config, key):
                    setattr(self.style_config, key, value)
    
    async def _mode_evaluation_loop(self) -> None:
        """Periodically evaluate and potentially switch modes."""
        while self._running:
            await asyncio.sleep(60)  # Evaluate every minute
            
            for symbol in list(self._market_metrics.keys()):
                await self._evaluate_mode(symbol)
            
            # Publish current mode
            await self._publish(EventType.AGENT_HEARTBEAT, {
                "agent": self.name,
                "status": self.status.value,
                "current_mode": self._current_mode.value,
                "mode_performance": {
                    m.value: p for m, p in self._mode_performance.items()
                }
            })
    
    async def _evaluate_mode(self, symbol: str) -> None:
        """Evaluate if mode switch is needed for a symbol."""
        metrics = self._market_metrics.get(symbol, {})
        if not metrics or len(metrics.get("returns", [])) < 20:
            return
        
        # Check cooldown
        if self._last_switch and (datetime.utcnow() - self._last_switch).total_seconds() < self.style_config.cooldown_hours * 3600:
            return
        
        # Calculate metrics
        returns = list(metrics["returns"])
        volumes = list(metrics.get("volumes", [1]))
        candles = list(metrics.get("candles", []))
        
        # Volatility (ATR proxy)
        volatility = np.std(returns) * np.sqrt(288)  # Annualized from 5m
        
        # Trend strength (from bias/confluence)
        bias_conf = metrics.get("bias_confidence", 0.5)
        confluence_result = metrics.get("confluence_result", "neutral")
        confluence_conf = metrics.get("confluence_confidence", 0.5)
        
        trend_strength = bias_conf
        if confluence_result in ["strong_bullish", "strong_bearish"]:
            trend_strength = max(trend_strength, confluence_conf)
        
        # Volume ratio
        avg_volume = np.mean(volumes[-20:]) if len(volumes) >= 20 else 1
        current_volume = volumes[-1] if volumes else 1
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
        
        # Determine recommended mode
        recommended_mode = self._current_mode
        confidence = 0.5
        reasoning_parts = []
        
        # High volatility + high volume -> scalping
        if volatility > self.style_config.volatility_threshold_high and volume_ratio > self.style_config.volume_threshold:
            recommended_mode = TradingMode.SCALPING
            confidence = 0.8
            reasoning_parts.append(f"High vol ({volatility:.3f}) + high volume ({volume_ratio:.1f}x)")
        
        # Low volatility + strong trend -> swing
        elif volatility < self.style_config.volatility_threshold_low and trend_strength > self.style_config.trend_threshold:
            recommended_mode = TradingMode.SWING
            confidence = 0.8
            reasoning_parts.append(f"Low vol ({volatility:.3f}) + strong trend ({trend_strength:.2f})")
        
        # Medium conditions -> check performance
        else:
            # Use historical performance to decide
            scalping_perf = self._mode_performance[TradingMode.SCALPING]
            swing_perf = self._mode_performance[TradingMode.SWING]
            
            scalping_wr = scalping_perf["wins"] / max(scalping_perf["trades"], 1)
            swing_wr = swing_perf["wins"] / max(swing_perf["trades"], 1)
            
            if scalping_wr > swing_wr + 0.1:
                recommended_mode = TradingMode.SCALPING
                reasoning_parts.append(f"Scalping outperforming ({scalping_wr:.1%} vs {swing_wr:.1%})")
            elif swing_wr > scalping_wr + 0.1:
                recommended_mode = TradingMode.SWING
                reasoning_parts.append(f"Swing outperforming ({swing_wr:.1%} vs {scalping_wr:.1%})")
            else:
                recommended_mode = TradingMode.HYBRID
                reasoning_parts.append("Mixed conditions - hybrid mode")
            
            confidence = 0.6
        
        # Switch if different and confident
        if recommended_mode != self._current_mode and confidence > 0.7:
            await self._switch_mode(recommended_mode, "; ".join(reasoning_parts))
    
    async def _switch_mode(self, new_mode: TradingMode, reasoning: str) -> None:
        """Switch trading mode."""
        old_mode = self._current_mode
        self._current_mode = new_mode
        self._last_switch = datetime.utcnow()
        
        self._mode_history.append({
            "from": old_mode.value,
            "to": new_mode.value,
            "timestamp": self._last_switch,
            "reasoning": reasoning
        })
        
        # Keep last 50 switches
        if len(self._mode_history) > 50:
            self._mode_history = self._mode_history[-50:]
        
        # Publish mode switch event
        params = self._get_mode_parameters(new_mode)
        
        await self._publish(EventType.MODE_SWITCH, {
            "old_mode": old_mode.value,
            "new_mode": new_mode.value,
            "reasoning": reasoning,
            "parameters": params,
            "timestamp": self._last_switch.isoformat()
        })
        
        # Also publish specific mode events
        if new_mode == TradingMode.SCALPING:
            await self._publish(EventType.SCALPING_MODE, {"parameters": params})
        elif new_mode == TradingMode.SWING:
            await self._publish(EventType.SWING_MODE, {"parameters": params})
    
    def _get_mode_parameters(self, mode: TradingMode) -> Dict[str, Any]:
        """Get trading parameters for a mode."""
        if mode == TradingMode.SCALPING:
            return {
                "max_hold_minutes": self.style_config.scalping_max_hold_minutes,
                "target_pct": self.style_config.scalping_target_pct,
                "stop_pct": self.style_config.scalping_stop_pct,
                "timeframes": ["1m", "5m"],
                "min_confluence": "bullish",
                "leverage_multiplier": 1.5
            }
        elif mode == TradingMode.SWING:
            return {
                "min_hold_hours": self.style_config.swing_min_hold_hours,
                "max_hold_days": self.style_config.swing_max_hold_days,
                "target_pct": self.style_config.swing_target_pct,
                "stop_pct": self.style_config.swing_stop_pct,
                "timeframes": ["15m", "1h", "4h"],
                "min_confluence": "strong_bullish",
                "leverage_multiplier": 1.0
            }
        else:  # HYBRID
            return {
                "scalping_allocation": 0.4,
                "swing_allocation": 0.6,
                "scalping_params": self._get_mode_parameters(TradingMode.SCALPING),
                "swing_params": self._get_mode_parameters(TradingMode.SWING)
            }
    
    def get_current_parameters(self) -> Dict[str, Any]:
        """Get parameters for current mode."""
        return self._get_mode_parameters(self._current_mode)
    
    def get_mode(self) -> TradingMode:
        """Get current trading mode."""
        return self._current_mode


# Need numpy for std
import numpy as np