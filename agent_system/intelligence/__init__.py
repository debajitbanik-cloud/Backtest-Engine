"""
Intelligence Layer — Google ADK agents, Root Supervisor, MCP tools, Model abstraction.
"""
from __future__ import annotations

from intelligence.agents import (
    RootSupervisor,
    MarketResearchAgent,
    FeatureResearchAgent,
    StrategyAgent,
    ValidationAgent,
    RiskAgent,
    ReportAgent,
    create_root_supervisor,
)
from intelligence.mcp import MCPToolset, QuantMCPServer, create_quant_mcp_server
from intelligence.models import ModelProvider, DeepSeekProvider, OpenAICompatibleProvider

__all__ = [
    "RootSupervisor",
    "MarketResearchAgent",
    "FeatureResearchAgent",
    "StrategyAgent",
    "ValidationAgent",
    "RiskAgent",
    "ReportAgent",
    "create_root_supervisor",
    "MCPToolset",
    "QuantMCPServer",
    "create_quant_mcp_server",
    "ModelProvider",
    "DeepSeekProvider",
    "OpenAICompatibleProvider",
]