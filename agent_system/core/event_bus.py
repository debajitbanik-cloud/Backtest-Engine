"""
Event Bus for inter-agent communication using pub-sub pattern.
"""
from __future__ import annotations
import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set
from enum import Enum
import uuid


class EventType(Enum):
    """System event types for agent communication."""
    # Market data events
    MARKET_TICK = "market_tick"
    MARKET_CANDLE = "market_candle"
    ORDERBOOK_UPDATE = "orderbook_update"
    
    # Signal events
    BIAS_SIGNAL = "bias_signal"
    CONFLUENCE_SIGNAL = "confluence_signal"
    LEVERAGE_ADJUSTMENT = "leverage_adjustment"
    TIMEFRAME_RECOMMENDATION = "timeframe_recommendation"
    
    # Position events
    POSITION_OPEN = "position_open"
    POSITION_CLOSE = "position_close"
    POSITION_UPDATE = "position_update"
    POSITION_SIZING = "position_sizing"
    
    # Risk events
    RISK_ALERT = "risk_alert"
    RISK_MITIGATION = "risk_mitigation"
    STOP_LOSS_TRIGGERED = "stop_loss_triggered"
    MARGIN_CALL = "margin_call"
    
    # Style/Mode events
    MODE_SWITCH = "mode_switch"
    SCALPING_MODE = "scalping_mode"
    SWING_MODE = "swing_mode"
    
    # Trade execution
    TRADE_EXECUTED = "trade_executed"
    TRADE_REJECTED = "trade_rejected"
    
    # Option signals
    OPTION_SIGNAL = "option_signal"
    OPTION_POSITION_UPDATE = "option_position_update"
    
    # XAU scalper signals
    XAU_SCALP_SIGNAL = "xau_scalp_signal"
    
    # Reporting & Optimization
    TRADE_LOG = "trade_log"
    DAILY_REPORT = "daily_report"
    OPTIMIZATION_UPDATE = "optimization_update"
    AGENT_TUNING = "agent_tuning"
    
    # System events
    AGENT_REGISTERED = "agent_registered"
    AGENT_HEARTBEAT = "agent_heartbeat"
    SYSTEM_SHUTDOWN = "system_shutdown"


@dataclass
class Event:
    """Base event structure."""
    type: EventType
    payload: Dict[str, Any]
    source_agent: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: Optional[str] = None


class EventBus:
    """Async event bus for agent communication."""
    
    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable[[Event], Any]]] = defaultdict(list)
        self._agent_subscriptions: Dict[str, Set[EventType]] = defaultdict(set)
        self._event_history: List[Event] = []
        self._max_history = 10000
        self._lock = asyncio.Lock()
    
    async def subscribe(self, event_type: EventType, handler: Callable[[Event], Any], agent_name: str) -> None:
        """Subscribe an agent to an event type."""
        async with self._lock:
            self._subscribers[event_type].append(handler)
            self._agent_subscriptions[agent_name].add(event_type)
    
    async def unsubscribe(self, event_type: EventType, handler: Callable[[Event], Any], agent_name: str) -> None:
        """Unsubscribe an agent from an event type."""
        async with self._lock:
            if handler in self._subscribers[event_type]:
                self._subscribers[event_type].remove(handler)
            self._agent_subscriptions[agent_name].discard(event_type)
    
    async def publish(self, event: Event) -> None:
        """Publish an event to all subscribers."""
        async with self._lock:
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history = self._event_history[-self._max_history:]
            
            handlers = self._subscribers.get(event.type, []).copy()
        
        # Execute handlers outside lock to avoid deadlock
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                print(f"Error in event handler for {event.type}: {e}")
    
    async def publish_sync(self, event: Event) -> List[Any]:
        """Publish event and wait for all handlers, return results."""
        async with self._lock:
            handlers = self._subscribers.get(event.type, []).copy()
        
        results = []
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(event)
                else:
                    result = handler(event)
                results.append(result)
            except Exception as e:
                print(f"Error in event handler for {event.type}: {e}")
                results.append(None)
        return results
    
    def get_agent_subscriptions(self, agent_name: str) -> Set[EventType]:
        """Get all event types an agent is subscribed to."""
        return self._agent_subscriptions.get(agent_name, set())
    
    def get_recent_events(self, event_type: Optional[EventType] = None, limit: int = 100) -> List[Event]:
        """Get recent events, optionally filtered by type."""
        events = self._event_history
        if event_type:
            events = [e for e in events if e.type == event_type]
        return events[-limit:]


# Global event bus instance
event_bus = EventBus()