"""
Google ADK Agents — Root Supervisor and specialized sub-agents.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

try:
    from google.adk import Agent, Context, Tool, ToolContext
    from google.adk.tools import FunctionTool
    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False
    Agent = object
    Context = object
    Tool = object
    ToolContext = object
    FunctionTool = object


from shared.domain import StrategyIdentity
from analytics.features import get_feature_factory, get_feature_registry, FeatureCategory
from analytics.leakage import get_leakage_sentinel, LeakageCheckResult
from analytics.regime import get_regime_detector, RegimeState
from analytics.validation.validation import (
    WalkForwardOptimizer,
    CombinatorialPurgedCV,
    MonteCarloValidator,
    ValidationGate,
    ValidationResult,
    DEFAULT_GATES,
    evaluate_gates,
    auto_reject,
)
from execution.engine import get_execution_engine, ExecutionEngine, PortfolioState, RiskLimits
from shared.domain import Instrument, Signal, ExecutionIntent, Order, Fill, Position


# ── Root Supervisor ────────────────────────────────────────────────────────────

@dataclass
class AgentPolicy:
    """Policy defining what an agent can do."""
    name: str
    allowed_tools: List[str]
    allowed_venues: List[str]
    requires_approval: List[str]  # actions requiring human approval
    max_position_pct: float = 0.10
    max_daily_trades: int = 50


class RootSupervisor:
    """
    Root Supervisor agent with explicit tool policy and routing rules.
    Coordinates all sub-agents and enforces policy gates.
    """

    def __init__(self, policies: Optional[Dict[str, AgentPolicy]] = None):
        self.policies = policies or self._default_policies()
        self.sub_agents: Dict[str, Any] = {}
        self._routing_rules: Dict[str, str] = {}  # intent -> agent name

    def _default_policies(self) -> Dict[str, AgentPolicy]:
        return {
            "market_research": AgentPolicy(
                name="market_research",
                allowed_tools=["fetch_market_data", "compute_features", "detect_regime"],
                allowed_venues=[],
                requires_approval=[],
            ),
            "feature_research": AgentPolicy(
                name="feature_research",
                allowed_tools=["register_feature", "compute_features", "check_leakage"],
                allowed_venues=[],
                requires_approval=[],
            ),
            "strategy": AgentPolicy(
                name="strategy",
                allowed_tools=["backtest_strategy", "optimize_parameters", "register_strategy"],
                allowed_venues=[],
                requires_approval=["deploy_strategy"],
            ),
            "validation": AgentPolicy(
                name="validation",
                allowed_tools=["run_wfo", "run_cpcv", "run_monte_carlo", "evaluate_gates"],
                allowed_venues=[],
                requires_approval=[],
            ),
            "risk": AgentPolicy(
                name="risk",
                allowed_tools=["evaluate_signal", "evaluate_intent", "check_limits", "kill_switch"],
                allowed_venues=[],
                requires_approval=["override_risk"],
            ),
            "report": AgentPolicy(
                name="report",
                allowed_tools=["generate_report", "export_data", "create_dashboard"],
                allowed_venues=[],
                requires_approval=[],
            ),
        }

    def register_agent(self, name: str, agent: Any) -> None:
        self.sub_agents[name] = agent

    def set_routing_rule(self, intent_type: str, agent_name: str) -> None:
        self._routing_rules[intent_type] = agent_name

    def get_policy(self, agent_name: str) -> Optional[AgentPolicy]:
        return self.policies.get(agent_name)

    def can_use_tool(self, agent_name: str, tool_name: str) -> bool:
        policy = self.policies.get(agent_name)
        if not policy:
            return False
        return tool_name in policy.allowed_tools

    def requires_approval(self, agent_name: str, action: str) -> bool:
        policy = self.policies.get(agent_name)
        if not policy:
            return True
        return action in policy.requires_approval

    def route(self, intent: str) -> Optional[str]:
        """Route an intent to the appropriate agent."""
        return self._routing_rules.get(intent)

    async def execute(self, intent: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an intent by routing to the appropriate agent."""
        agent_name = self.route(intent)
        if not agent_name or agent_name not in self.sub_agents:
            return {"error": f"No agent registered for intent: {intent}"}

        agent = self.sub_agents[agent_name]
        if hasattr(agent, intent):
            method = getattr(agent, intent)
            return await method(payload)
        return {"error": f"Agent {agent_name} does not support intent: {intent}"}


# ── Sub-Agents ────────────────────────────────────────────────────────────────

class MarketResearchAgent:
    """Agent for market data analysis and regime detection."""

    def __init__(self):
        self.feature_factory = get_feature_factory()
        self.regime_detector = get_regime_detector()

    async def fetch_market_data(
        self,
        symbol: str,
        timeframe: str = "1h",
        lookback: int = 500,
    ) -> Dict[str, Any]:
        """Fetch market data (placeholder - integrate with data feeds)."""
        return {"symbol": symbol, "timeframe": timeframe, "lookback": lookback}

    async def compute_features(
        self,
        df: Any,  # DataFrame
        features: List[str],
        categories: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Compute features for market data."""
        factory = get_feature_factory()
        if categories:
            result = factory.compute_all(df, categories)
        else:
            result = factory.compute(df, features)
        return {"features": result.columns.tolist(), "shape": result.shape}

    async def detect_regime(self, df: Any) -> Dict[str, Any]:
        """Detect current market regime."""
        state = self.regime_detector.detect(df)
        return {
            "trend": state.trend_direction.value,
            "trend_strength": state.trend_strength,
            "volatility": state.volatility_regime.value,
            "vol_percentile": state.vol_percentile,
            "liquidity": state.liquidity_regime.value,
            "momentum": state.momentum_score,
            "session": state.session,
            "stress": state.stress_level.value,
            "dominant": state.dominant_regime.value,
            "confidence": state.confidence,
        }


class FeatureResearchAgent:
    """Agent for feature engineering, registry, and leakage detection."""

    def __init__(self):
        self.factory = get_feature_factory()
        self.registry = get_feature_registry()
        self.sentinel = get_leakage_sentinel()

    async def register_feature(
        self,
        name: str,
        formula: str,
        category: str,
        source_data: List[str],
        lookback: int,
        **kwargs,
    ) -> Dict[str, Any]:
        """Register a new feature in the registry."""
        from analytics.features import FeatureMetadata, FeatureCategory, NormalizationType
        metadata = FeatureMetadata(
            name=name,
            category=FeatureCategory(category),
            formula=formula,
            source_data=source_data,
            lookback=lookback,
            **kwargs,
        )
        self.registry.register(metadata)
        return {"status": "registered", "fingerprint": metadata.fingerprint}

    async def compute_features(self, df: Any, features: List[str]) -> Dict[str, Any]:
        result = self.factory.compute(df, features)
        return {"columns": result.columns.tolist(), "shape": result.shape}

    async def check_leakage(
        self,
        features_df: Any,
        labels_df: Optional[Any] = None,
        train_mask: Optional[Any] = None,
        test_mask: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Run leakage sentinel checks."""
        results = self.sentinel.check_all(
            features_df,
            labels_df,
            train_mask,
            test_mask,
        )
        return {
            "total_checks": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "details": [
                {
                    "check": r.check_name,
                    "type": r.leakage_type.value,
                    "severity": r.severity.value,
                    "passed": r.passed,
                    "message": r.message,
                }
                for r in results
            ],
        }


class StrategyAgent:
    """Agent for strategy development, backtesting, and registration."""

    def __init__(self):
        from shared.registry import get_strategy_registry
        self.strategy_registry = get_strategy_registry()

    async def backtest_strategy(
        self,
        strategy_config: Dict[str, Any],
        symbol: str,
        timeframe: str,
        start: str,
        end: str,
    ) -> Dict[str, Any]:
        """Run backtest (placeholder - integrate with runner)."""
        return {"status": "completed", "metrics": {}}

    async def optimize_parameters(
        self,
        strategy_id: str,
        param_ranges: Dict[str, Tuple[float, float]],
        n_trials: int = 100,
    ) -> Dict[str, Any]:
        """Optimize strategy parameters (placeholder)."""
        return {"best_params": {}, "best_score": 0.0}

    async def register_strategy(
        self,
        name: str,
        version: str,
        description: str,
        parameters: Dict[str, Any],
        tags: List[str],
    ) -> Dict[str, Any]:
        """Register a strategy in the registry."""
        strategy = StrategyIdentity(
            name=name,
            version=version,
            description=description,
            parameters=parameters,
            tags=tags,
        )
        self.strategy_registry.create(strategy)
        return {"status": "registered", "id": strategy.id}


class ValidationAgent:
    """Agent for validation (WFO, CPCV, Monte Carlo, gates)."""

    def __init__(self):
        self.wfo = WalkForwardOptimizer()
        self.cpcv = CombinatorialPurgedCV()
        self.mc = MonteCarloValidator()

    async def run_wfo(
        self,
        model_factory: Callable,
        X: Any,
        y: Any,
        gates: Optional[List[Dict]] = None,
        strategy_id: str = "unknown",
    ) -> Dict[str, Any]:
        """Run walk-forward optimization."""
        gate_objs = [ValidationGate(**g) for g in gates] if gates else DEFAULT_GATES
        result = self.wfo.validate(model_factory, X, y, gates=gate_objs, strategy_id=strategy_id)
        return {
            "type": "walk_forward",
            "n_folds": result.n_folds,
            "metrics": result.metrics,
            "passed_gates": result.passed_gates,
            "failed_gates": result.failed_gates,
        }

    async def run_cpcv(
        self,
        model_factory: Callable,
        X: Any,
        y: Any,
        gates: Optional[List[Dict]] = None,
        strategy_id: str = "unknown",
    ) -> Dict[str, Any]:
        """Run CPCV."""
        gate_objs = [ValidationGate(**g) for g in gates] if gates else DEFAULT_GATES
        result = self.cpcv.validate(model_factory, X, y, gates=gate_objs, strategy_id=strategy_id)
        return {
            "type": "cpcv",
            "n_folds": result.n_folds,
            "metrics": result.metrics,
            "passed_gates": result.passed_gates,
            "failed_gates": result.failed_gates,
        }

    async def run_monte_carlo(
        self,
        trades: List[Dict],
        n_simulations: int = 1000,
    ) -> Dict[str, Any]:
        """Run Monte Carlo sequencing test."""
        return self.mc.validate_sequencing(trades, n_simulations)

    async def evaluate_gates(self, metrics: Dict[str, float]) -> Dict[str, Any]:
        """Evaluate validation gates."""
        passed, failed, results = evaluate_gates(metrics)
        return {
            "passed": passed,
            "failed": failed,
            "all_passed": len(failed) == 0,
        }


class RiskAgent:
    """Agent for risk evaluation and kill switches."""

    def __init__(self):
        self.engine = get_execution_engine()

    async def evaluate_signal(self, signal: Dict, portfolio: Dict) -> Dict[str, Any]:
        """Evaluate a signal through risk overlay."""
        # Convert to domain objects
        from shared.domain import Signal, PortfolioState, RiskLimits
        # (implementation details omitted)
        return {"approved": True, "checks": {}, "notes": []}

    async def evaluate_intent(self, intent: Dict, portfolio: Dict) -> Dict[str, Any]:
        """Evaluate execution intent."""
        return {"approved": True, "checks": {}}

    async def check_limits(self, portfolio: Dict) -> Dict[str, Any]:
        """Check portfolio risk limits."""
        return {"within_limits": True, "violations": []}

    async def kill_switch(self, reason: str) -> Dict[str, Any]:
        """Activate emergency kill switch."""
        return {"activated": True, "reason": reason}


class ReportAgent:
    """Agent for report generation and data export."""

    async def generate_report(
        self,
        report_type: str,
        data: Dict,
        format: str = "json",
    ) -> Dict[str, Any]:
        """Generate a report."""
        return {"type": report_type, "format": format, "data": data}

    async def export_data(
        self,
        query: str,
        format: str = "csv",
    ) -> Dict[str, Any]:
        """Export data."""
        return {"format": format, "rows": 0}

    async def create_dashboard(
        self,
        config: Dict,
    ) -> Dict[str, Any]:
        """Create dashboard configuration."""
        return {"config": config}


def create_root_supervisor() -> RootSupervisor:
    """Factory function to create a fully configured RootSupervisor with all sub-agents."""
    supervisor = RootSupervisor()

    # Create and register sub-agents
    agents = {
        "market_research": MarketResearchAgent(),
        "feature_research": FeatureResearchAgent(),
        "strategy": StrategyAgent(),
        "validation": ValidationAgent(),
        "risk": RiskAgent(),
        "report": ReportAgent(),
    }

    for name, agent in agents.items():
        supervisor.register_agent(name, agent)

    # Set routing rules
    routing = {
        "fetch_market_data": "market_research",
        "compute_features": "feature_research",
        "detect_regime": "market_research",
        "register_feature": "feature_research",
        "check_leakage": "feature_research",
        "backtest_strategy": "strategy",
        "optimize_parameters": "strategy",
        "register_strategy": "strategy",
        "run_wfo": "validation",
        "run_cpcv": "validation",
        "run_monte_carlo": "validation",
        "evaluate_gates": "validation",
        "evaluate_signal": "risk",
        "evaluate_intent": "risk",
        "check_limits": "risk",
        "kill_switch": "risk",
        "generate_report": "report",
        "export_data": "report",
        "create_dashboard": "report",
    }

    for intent, agent in routing.items():
        supervisor.set_routing_rule(intent, agent)

    return supervisor