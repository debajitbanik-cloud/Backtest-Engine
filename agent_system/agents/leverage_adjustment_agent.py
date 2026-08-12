"""
Leverage Adjustment Agent
Adjusts leverage based on margin requirements and market conditions.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from collections import deque

from core.base_agent import BaseAgent, AgentConfig, AgentStatus
from core.event_bus import EventBus, Event, EventType, event_bus


@dataclass
class MarginSnapshot:
    """Snapshot of margin state at a point in time."""
    timestamp: datetime
    used_margin: float
    available_margin: float
    margin_ratio: float  # used / total
    maintenance_margin: float
    initial_margin: float
    leverage: float
    position_value: float


@dataclass
class LeverageConfig:
    """Configuration for leverage adjustment."""
    max_leverage: float = 20.0
    min_leverage: float = 1.0
    margin_warning_threshold: float = 0.7  # 70% margin used
    margin_critical_threshold: float = 0.85  # 85% margin used
    margin_liquidation_threshold: float = 0.95  # 95% margin used
    adjustment_step: float = 0.5  # Leverage adjustment step
    cooldown_seconds: int = 60  # Minimum time between adjustments
    lookback_periods: int = 20  # Periods for volatility calculation


class LeverageAdjustmentAgent(BaseAgent):
    """
    Monitors margin requirements and adjusts leverage dynamically.
    
    Responsibilities:
    - Track margin usage across positions
    - Detect high margin requirement periods
    - Reduce leverage proactively before margin calls
    - Increase leverage when margin is healthy
    - Coordinate with RiskCheckingAgent for emergency reductions
    """
    
    def __init__(self, config: AgentConfig, event_bus: EventBus = None):
        super().__init__(config, event_bus)
        
        # Parse agent-specific config
        leverage_config = config.config.get("leverage", {})
        self.leverage_config = LeverageConfig(**leverage_config)
        
        # State
        self._margin_history: deque = deque(maxlen=self.leverage_config.lookback_periods)
        self._current_leverage: Dict[str, float] = {}  # symbol -> leverage
        self._last_adjustment: Dict[str, datetime] = {}
        self._position_margins: Dict[str, MarginSnapshot] = {}
        self._margin_alerts_active: Dict[str, bool] = {}
        
        # Subscribe to relevant events
        self.config.subscriptions = [
            EventType.MARKET_TICK,
            EventType.POSITION_UPDATE,
            EventType.MARGIN_CALL,
            EventType.RISK_ALERT,
            EventType.AGENT_TUNING,
        ]
    
    async def initialize(self) -> None:
        """Initialize the agent."""
        self.status = AgentStatus.RUNNING
        await self._subscribe_to_events()
        
        # Publish registration
        await self._publish(EventType.AGENT_REGISTERED, {
            "agent": self.name,
            "capabilities": ["leverage_adjustment", "margin_monitoring"],
            "config": self.leverage_config.__dict__
        })
    
    async def start(self) -> None:
        """Start the monitoring loop."""
        self._running = True
        asyncio.create_task(self._monitoring_loop())
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
        elif event.type == EventType.POSITION_UPDATE:
            await self._on_position_update(event)
        elif event.type == EventType.MARGIN_CALL:
            await self._on_margin_call(event)
        elif event.type == EventType.RISK_ALERT:
            await self._on_risk_alert(event)
        elif event.type == EventType.AGENT_TUNING:
            await self._on_tuning(event)
    
    async def _on_market_tick(self, event: Event) -> None:
        """Process market tick for margin recalculation."""
        payload = event.payload
        symbol = payload.get("symbol")
        price = payload.get("price")
        
        if not symbol or not price:
            return
        
        # Recalculate margin for positions in this symbol
        if symbol in self._position_margins:
            await self._recalculate_margin(symbol, price)
    
    async def _on_position_update(self, event: Event) -> None:
        """Handle position updates."""
        payload = event.payload
        symbol = payload.get("symbol")
        position = payload.get("position", {})
        
        if not symbol:
            return
        
        # Update position margin snapshot
        margin_snapshot = MarginSnapshot(
            timestamp=datetime.utcnow(),
            used_margin=position.get("used_margin", 0),
            available_margin=position.get("available_margin", 0),
            margin_ratio=position.get("margin_ratio", 0),
            maintenance_margin=position.get("maintenance_margin", 0),
            initial_margin=position.get("initial_margin", 0),
            leverage=position.get("leverage", 1),
            position_value=position.get("position_value", 0)
        )
        
        self._position_margins[symbol] = margin_snapshot
        self._margin_history.append(margin_snapshot)
        
        # Check if leverage adjustment needed
        await self._evaluate_leverage_adjustment(symbol, margin_snapshot)
    
    async def _on_margin_call(self, event: Event) -> None:
        """Emergency leverage reduction on margin call."""
        payload = event.payload
        symbol = payload.get("symbol")
        
        if symbol and symbol in self._current_leverage:
            current = self._current_leverage[symbol]
            new_leverage = max(self.leverage_config.min_leverage, current * 0.5)
            await self._adjust_leverage(symbol, new_leverage, "margin_call_emergency")
    
    async def _on_risk_alert(self, event: Event) -> None:
        """Handle risk alerts from RiskCheckingAgent."""
        payload = event.payload
        alert_type = payload.get("alert_type")
        symbol = payload.get("symbol")
        
        if alert_type in ["high_drawdown", "consecutive_losses"] and symbol:
            # Reduce leverage as precaution
            if symbol in self._current_leverage:
                current = self._current_leverage[symbol]
                new_leverage = max(self.leverage_config.min_leverage, current * 0.7)
                await self._adjust_leverage(symbol, new_leverage, f"risk_alert_{alert_type}")
    
    async def _on_tuning(self, event: Event) -> None:
        """Handle tuning parameters from ManagerAgent."""
        payload = event.payload
        if payload.get("target_agent") == self.name:
            params = payload.get("parameters", {})
            for key, value in params.items():
                if hasattr(self.leverage_config, key):
                    setattr(self.leverage_config, key, value)
    
    async def _recalculate_margin(self, symbol: str, current_price: float) -> None:
        """Recalculate margin based on current price."""
        snapshot = self._position_margins.get(symbol)
        if not snapshot:
            return
        
        # Simplified margin recalculation (would use actual position data in production)
        position_value = snapshot.position_value * (current_price / snapshot.position_value) if snapshot.position_value > 0 else 0
        used_margin = position_value / snapshot.leverage if snapshot.leverage > 0 else 0
        
        updated_snapshot = MarginSnapshot(
            timestamp=datetime.utcnow(),
            used_margin=used_margin,
            available_margin=snapshot.available_margin,
            margin_ratio=used_margin / (used_margin + snapshot.available_margin) if (used_margin + snapshot.available_margin) > 0 else 0,
            maintenance_margin=snapshot.maintenance_margin,
            initial_margin=snapshot.initial_margin,
            leverage=snapshot.leverage,
            position_value=position_value
        )
        
        self._position_margins[symbol] = updated_snapshot
        await self._evaluate_leverage_adjustment(symbol, updated_snapshot)
    
    async def _evaluate_leverage_adjustment(self, symbol: str, snapshot: MarginSnapshot) -> None:
        """Evaluate if leverage adjustment is needed."""
        margin_ratio = snapshot.margin_ratio
        current_leverage = snapshot.leverage
        
        # Check cooldown
        last_adj = self._last_adjustment.get(symbol)
        if last_adj and (datetime.utcnow() - last_adj).total_seconds() < self.leverage_config.cooldown_seconds:
            return
        
        new_leverage = current_leverage
        reason = None
        
        if margin_ratio >= self.leverage_config.margin_liquidation_threshold:
            # Critical - reduce aggressively
            new_leverage = max(self.leverage_config.min_leverage, current_leverage * 0.3)
            reason = "liquidation_risk"
        elif margin_ratio >= self.leverage_config.margin_critical_threshold:
            # High margin usage - reduce
            new_leverage = max(self.leverage_config.min_leverage, current_leverage * 0.6)
            reason = "critical_margin"
        elif margin_ratio >= self.leverage_config.margin_warning_threshold:
            # Warning - slight reduction
            new_leverage = max(self.leverage_config.min_leverage, current_leverage * 0.85)
            reason = "warning_margin"
        elif margin_ratio < 0.3 and current_leverage < self.leverage_config.max_leverage:
            # Healthy margin - can increase leverage
            new_leverage = min(self.leverage_config.max_leverage, current_leverage + self.leverage_config.adjustment_step)
            reason = "healthy_margin_increase"
        
        if new_leverage != current_leverage and reason:
            await self._adjust_leverage(symbol, new_leverage, reason)
    
    async def _adjust_leverage(self, symbol: str, new_leverage: float, reason: str) -> None:
        """Adjust leverage for a symbol."""
        old_leverage = self._current_leverage.get(symbol, 1.0)
        self._current_leverage[symbol] = new_leverage
        self._last_adjustment[symbol] = datetime.utcnow()
        
        # Publish leverage adjustment event
        await self._publish(EventType.LEVERAGE_ADJUSTMENT, {
            "symbol": symbol,
            "old_leverage": old_leverage,
            "new_leverage": new_leverage,
            "reason": reason,
            "margin_ratio": self._position_margins.get(symbol, MarginSnapshot(
                timestamp=datetime.utcnow(), used_margin=0, available_margin=0,
                margin_ratio=0, maintenance_margin=0, initial_margin=0, leverage=1, position_value=0
            )).margin_ratio
        })
        
        # Update metrics
        self._metrics[f"leverage_{symbol}"] = new_leverage
        self._metrics[f"last_adjustment_{symbol}"] = reason
    
    async def _monitoring_loop(self) -> None:
        """Periodic margin health check."""
        while self._running:
            await asyncio.sleep(10)  # Check every 10 seconds
            
            for symbol, snapshot in self._position_margins.items():
                await self._evaluate_leverage_adjustment(symbol, snapshot)
            
            # Publish margin health summary
            await self._publish(EventType.AGENT_HEARTBEAT, {
                "agent": self.name,
                "status": self.status.value,
                "leverages": self._current_leverage.copy(),
                "margin_ratios": {s: m.margin_ratio for s, m in self._position_margins.items()}
            })