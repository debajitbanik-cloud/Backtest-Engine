"""
Execution package — contracts, adapters, and engine.
"""
from __future__ import annotations

from execution.contracts import (
    VenueAdapter,
    RiskOverlay,
    PortfolioState,
    RiskLimits,
    RiskCheckResult,
    adapter_registry,
    AdapterRegistry,
)
from execution.engine import (
    ExecutionEngine,
    ExecutionConfig,
    DefaultRiskOverlay,
    get_execution_engine,
)

__all__ = [
    "VenueAdapter",
    "RiskOverlay",
    "PortfolioState",
    "RiskLimits",
    "RiskCheckResult",
    "adapter_registry",
    "AdapterRegistry",
    "ExecutionEngine",
    "ExecutionConfig",
    "DefaultRiskOverlay",
    "get_execution_engine",
]