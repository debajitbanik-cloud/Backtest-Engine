"""
Configuration loader for the agent system.
"""
from __future__ import annotations
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class SystemConfig:
    name: str
    version: str
    environment: str
    log_level: str
    data_dir: str
    report_dir: str


@dataclass
class EventBusConfig:
    max_history: int
    heartbeat_interval: int


@dataclass
class AgentConfig:
    enabled: bool
    config: Dict[str, Any]


class ConfigLoader:
    """Load and manage system configuration."""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent / "settings.yaml"
        self.config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        self._load()
    
    def _load(self) -> None:
        """Load configuration from YAML file, falling back to settings.yaml.example."""
        path = self.config_path
        if not path.exists():
            example = path.with_name(path.name + '.example')
            if example.exists():
                path = example
        with open(path, 'r') as f:
            self._config = yaml.safe_load(f)
    
    def get_system_config(self) -> SystemConfig:
        """Get system configuration."""
        sys_cfg = self._config.get("system", {})
        return SystemConfig(**sys_cfg)
    
    def get_event_bus_config(self) -> EventBusConfig:
        """Get event bus configuration."""
        eb_cfg = self._config.get("event_bus", {})
        return EventBusConfig(**eb_cfg)
    
    def get_agent_config(self, agent_name: str) -> AgentConfig:
        """Get configuration for a specific agent."""
        agents = self._config.get("agents", {})
        agent_cfg = agents.get(agent_name, {})
        return AgentConfig(
            enabled=agent_cfg.get("enabled", True),
            config=agent_cfg  # Full raw config so agents can find their nested keys
        )
    
    def get_data_feed_config(self, feed_name: str) -> Dict[str, Any]:
        """Get data feed configuration."""
        feeds = self._config.get("data_feed", {})
        return feeds.get(feed_name, {})
    
    def get_delta_config(self) -> Dict[str, Any]:
        """Get Delta Exchange configuration."""
        return self._config.get("delta_exchange", {})
    
    def get_trading_config(self) -> Dict[str, Any]:
        """Get trading configuration."""
        return self._config.get("trading", {})
    
    def get_all_agent_configs(self) -> Dict[str, AgentConfig]:
        """Get all agent configurations."""
        agents = self._config.get("agents", {})
        result = {}
        for name, cfg in agents.items():
            result[name] = AgentConfig(
                enabled=cfg.get("enabled", True),
                config=cfg  # Full raw config so agents can find their nested keys
            )
        return result


# Global config instance
config_loader = ConfigLoader()