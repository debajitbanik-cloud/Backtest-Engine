"""
Agent registry for managing all agents in the system.
"""
from __future__ import annotations
import asyncio
from typing import Dict, List, Optional, Type
from dataclasses import dataclass, field

from core.base_agent import BaseAgent, AgentConfig, AgentStatus
from core.event_bus import EventBus, EventType, event_bus


@dataclass
class AgentInfo:
    """Information about a registered agent."""
    agent: BaseAgent
    config: AgentConfig
    status: AgentStatus = AgentStatus.INITIALIZING
    dependencies: List[str] = field(default_factory=list)


class AgentRegistry:
    """Central registry for all agents in the trading system."""
    
    def __init__(self, event_bus: EventBus = None):
        self.event_bus = event_bus or event_bus
        self._agents: Dict[str, AgentInfo] = {}
        self._startup_order: List[str] = []
        self._shutdown_order: List[str] = []
    
    def register(self, agent: BaseAgent, dependencies: List[str] = None) -> None:
        """Register an agent with optional dependencies."""
        if agent.name in self._agents:
            raise ValueError(f"Agent {agent.name} already registered")
        
        self._agents[agent.name] = AgentInfo(
            agent=agent,
            config=agent.config,
            dependencies=dependencies or []
        )
        
        # Build startup/shutdown order based on dependencies
        self._rebuild_order()
    
    def _rebuild_order(self) -> None:
        """Rebuild startup/shutdown order using topological sort."""
        # Simple topological sort for dependency resolution
        visited = set()
        temp = set()
        order = []
        
        def visit(name: str):
            if name in temp:
                raise ValueError(f"Circular dependency detected involving {name}")
            if name in visited:
                return
            temp.add(name)
            for dep in self._agents[name].dependencies:
                if dep in self._agents:
                    visit(dep)
            temp.remove(name)
            visited.add(name)
            order.append(name)
        
        for name in self._agents:
            if name not in visited:
                visit(name)
        
        self._startup_order = order
        self._shutdown_order = list(reversed(order))
    
    async def initialize_all(self) -> None:
        """Initialize all agents in dependency order."""
        for name in self._startup_order:
            agent_info = self._agents[name]
            if agent_info.config.enabled:
                agent_info.status = AgentStatus.INITIALIZING
                await agent_info.agent.initialize()
                agent_info.status = AgentStatus.RUNNING
    
    async def start_all(self) -> None:
        """Start all agents in dependency order."""
        for name in self._startup_order:
            agent_info = self._agents[name]
            if agent_info.config.enabled:
                await agent_info.agent.start()
    
    async def stop_all(self) -> None:
        """Stop all agents in reverse dependency order."""
        for name in self._shutdown_order:
            agent_info = self._agents[name]
            if agent_info.config.enabled:
                agent_info.status = AgentStatus.STOPPED
                await agent_info.agent.stop()
    
    def get_agent(self, name: str) -> Optional[BaseAgent]:
        """Get agent by name."""
        info = self._agents.get(name)
        return info.agent if info else None
    
    def get_all_agents(self) -> Dict[str, BaseAgent]:
        """Get all registered agents."""
        return {name: info.agent for name, info in self._agents.items()}
    
    def get_status(self) -> Dict[str, Dict]:
        """Get status of all agents."""
        return {
            name: {
                "status": info.status.value,
                "enabled": info.config.enabled,
                "dependencies": info.dependencies,
                "metrics": info.agent.get_metrics()
            }
            for name, info in self._agents.items()
        }


# Global registry instance
agent_registry = AgentRegistry()