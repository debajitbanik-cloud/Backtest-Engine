"""
Base agent class for all trading agents.
"""
from __future__ import annotations
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from enum import Enum

from core.event_bus import EventBus, Event, EventType, event_bus as _default_event_bus


class AgentStatus(Enum):
    """Agent lifecycle status."""
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class AgentConfig:
    """Base configuration for agents."""
    name: str
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    subscriptions: List[EventType] = field(default_factory=list)


class BaseAgent(ABC):
    """Abstract base class for all trading agents."""
    
    def __init__(self, config: AgentConfig, event_bus: EventBus = None):
        self.config = config
        self.name = config.name
        self.event_bus = event_bus or _default_event_bus
        self.status = AgentStatus.INITIALIZING
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._last_heartbeat = datetime.utcnow()
        self._metrics: Dict[str, Any] = {}
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize agent resources, connections, etc."""
        pass
    
    @abstractmethod
    async def start(self) -> None:
        """Start the agent's main loop."""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop the agent gracefully."""
        pass
    
    async def _subscribe_to_events(self) -> None:
        """Subscribe to configured event types."""
        for event_type in self.config.subscriptions:
            await self.event_bus.subscribe(event_type, self._handle_event, self.name)
    
    @abstractmethod
    async def _handle_event(self, event: Event) -> None:
        """Handle incoming events. Must be implemented by subclasses."""
        pass
    
    async def _publish(self, event_type: EventType, payload: Dict[str, Any], correlation_id: str = None) -> None:
        """Publish an event to the bus."""
        event = Event(
            type=event_type,
            payload=payload,
            source_agent=self.name,
            correlation_id=correlation_id
        )
        await self.event_bus.publish(event)
    
    async def _publish_sync(self, event_type: EventType, payload: Dict[str, Any], correlation_id: str = None) -> List[Any]:
        """Publish event and wait for responses."""
        event = Event(
            type=event_type,
            payload=payload,
            source_agent=self.name,
            correlation_id=correlation_id
        )
        return await self.event_bus.publish_sync(event)
    
    def update_heartbeat(self) -> None:
        """Update last heartbeat timestamp."""
        self._last_heartbeat = datetime.utcnow()
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get agent performance metrics."""
        return {
            "name": self.name,
            "status": self.status.value,
            "last_heartbeat": self._last_heartbeat.isoformat(),
            "metrics": self._metrics
        }
    
    async def _run_heartbeat(self, interval: int = 30) -> None:
        """Send periodic heartbeat events."""
        while self._running:
            await asyncio.sleep(interval)
            if self._running:
                self.update_heartbeat()
                await self._publish(EventType.AGENT_HEARTBEAT, {
                    "agent": self.name,
                    "status": self.status.value,
                    "metrics": self._metrics
                })