"""
MCP Tools and Quant MCP Server for deterministic quant operations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

try:
    from mcp import Server, Tool, Resource
    from mcp.types import TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    Server = object
    Tool = object
    Resource = object


class MCPToolset:
    """Collection of MCP tools for quant operations."""

    def __init__(self, name: str = "quant_tools"):
        self.name = name
        self._tools: Dict[str, Callable] = {}

    def register(self, name: str, fn: Callable, description: str = "", schema: Dict = None) -> None:
        """Register a function as an MCP tool."""
        self._tools[name] = {
            "fn": fn,
            "description": description,
            "schema": schema or {},
        }

    def get_tool(self, name: str) -> Optional[Callable]:
        tool = self._tools.get(name)
        return tool["fn"] if tool else None

    def list_tools(self) -> List[Dict]:
        return [
            {"name": name, "description": info["description"], "schema": info["schema"]}
            for name, info in self._tools.items()
        ]


class QuantMCPServer:
    """
    MCP Server exposing deterministic quant operations as tools.
    These tools can be called by ADK agents or any MCP client.
    """

    def __init__(self, name: str = "quant_mcp"):
        self.name = name
        self.toolset = MCPToolset("quant_operations")
        self._register_quant_tools()

    def _register_quant_tools(self) -> None:
        """Register all deterministic quant operations."""

        # Feature computation
        self.toolset.register(
            "compute_features",
            self._compute_features,
            "Compute technical features from OHLCV data",
            {
                "type": "object",
                "properties": {
                    "data": {"type": "array", "items": {"type": "object"}},
                    "features": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["data", "features"],
            },
        )

        self.toolset.register(
            "detect_regime",
            self._detect_regime,
            "Detect market regime from OHLCV data",
            {
                "type": "object",
                "properties": {
                    "data": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["data"],
            },
        )

        # Validation
        self.toolset.register(
            "run_wfo",
            self._run_wfo,
            "Run walk-forward optimization",
            {
                "type": "object",
                "properties": {
                    "model_config": {"type": "object"},
                    "X": {"type": "array", "items": {"type": "array"}},
                    "y": {"type": "array"},
                    "train_window": {"type": "integer"},
                    "test_window": {"type": "integer"},
                },
                "required": ["model_config", "X", "y"],
            },
        )

        self.toolset.register(
            "run_cpcv",
            self._run_cpcv,
            "Run combinatorial purged cross-validation",
            {
                "type": "object",
                "properties": {
                    "model_config": {"type": "object"},
                    "X": {"type": "array", "items": {"type": "array"}},
                    "y": {"type": "array"},
                    "n_splits": {"type": "integer", "default": 5},
                },
                "required": ["model_config", "X", "y"],
            },
        )

        self.toolset.register(
            "run_monte_carlo",
            self._run_monte_carlo,
            "Run Monte Carlo trade sequencing test",
            {
                "type": "object",
                "properties": {
                    "trades": {"type": "array", "items": {"type": "object"}},
                    "n_simulations": {"type": "integer", "default": 1000},
                },
                "required": ["trades"],
            },
        )

        self.toolset.register(
            "evaluate_gates",
            self._evaluate_gates,
            "Evaluate validation gates against metrics",
            {
                "type": "object",
                "properties": {
                    "metrics": {"type": "object"},
                    "gates": {"type": "array"},
                },
                "required": ["metrics"],
            },
        )

        # Risk
        self.toolset.register(
            "evaluate_risk",
            self._evaluate_risk,
            "Evaluate signal/intent through risk overlay",
            {
                "type": "object",
                "properties": {
                    "signal": {"type": "object"},
                    "portfolio": {"type": "object"},
                },
                "required": ["signal", "portfolio"],
            },
        )

        self.toolset.register(
            "check_limits",
            self._check_limits,
            "Check portfolio risk limits",
            {
                "type": "object",
                "properties": {
                    "portfolio": {"type": "object"},
                },
                "required": ["portfolio"],
            },
        )

        # Feature registry
        self.toolset.register(
            "register_feature",
            self._register_feature,
            "Register a feature in the feature registry",
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "formula": {"type": "string"},
                    "category": {"type": "string"},
                    "source_data": {"type": "array", "items": {"type": "string"}},
                    "lookback": {"type": "integer"},
                },
                "required": ["name", "formula", "category", "source_data", "lookback"],
            },
        )

        self.toolset.register(
            "check_leakage",
            self._check_leakage,
            "Run leakage sentinel on features",
            {
                "type": "object",
                "properties": {
                    "features": {"type": "array", "items": {"type": "object"}},
                    "labels": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["features"],
            },
        )

        # Strategy
        self.toolset.register(
            "backtest_strategy",
            self._backtest_strategy,
            "Run strategy backtest",
            {
                "type": "object",
                "properties": {
                    "strategy_config": {"type": "object"},
                    "symbol": {"type": "string"},
                    "timeframe": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                },
                "required": ["strategy_config", "symbol", "timeframe", "start", "end"],
            },
        )

    # ── Tool implementations (placeholder - connect to actual modules) ──────

    async def _compute_features(self, data: List[Dict], features: List[str]) -> Dict:
        from analytics.features import get_feature_factory
        import pandas as pd
        df = pd.DataFrame(data)
        factory = get_feature_factory()
        result = factory.compute(df, features)
        return {"columns": result.columns.tolist(), "shape": result.shape}

    async def _detect_regime(self, data: List[Dict]) -> Dict:
        from analytics.regime import get_regime_detector
        import pandas as pd
        df = pd.DataFrame(data)
        detector = get_regime_detector()
        state = detector.detect(df)
        return {
            "trend": state.trend_direction.value,
            "trend_strength": state.trend_strength,
            "volatility": state.volatility_regime.value,
            "momentum": state.momentum_score,
            "stress": state.stress_level.value,
            "dominant": state.dominant_regime.value,
        }

    async def _run_wfo(self, model_config: Dict, X: List, y: List,
                       train_window: int = 252, test_window: int = 63) -> Dict:
        from analytics.validation.validation import WalkForwardOptimizer
        import numpy as np
        wfo = WalkForwardOptimizer(train_window=train_window, test_window=test_window)

        def model_factory():
            # Would create model from config
            from sklearn.linear_model import LinearRegression
            return LinearRegression()

        X_arr = np.array(X)
        y_arr = np.array(y)
        result = wfo.validate(model_factory, X_arr, y_arr)
        return {"metrics": result.metrics, "passed_gates": result.passed_gates, "failed_gates": result.failed_gates}

    async def _run_cpcv(self, model_config: Dict, X: List, y: List, n_splits: int = 5) -> Dict:
        from analytics.validation.validation import CombinatorialPurgedCV
        import numpy as np
        cpcv = CombinatorialPurgedCV(n_splits=n_splits)

        def model_factory():
            from sklearn.linear_model import LinearRegression
            return LinearRegression()

        X_arr = np.array(X)
        y_arr = np.array(y)
        result = cpcv.validate(model_factory, X_arr, y_arr)
        return {"metrics": result.metrics, "passed_gates": result.passed_gates, "failed_gates": result.failed_gates}

    async def _run_monte_carlo(self, trades: List[Dict], n_simulations: int = 1000) -> Dict:
        from analytics.validation.validation import MonteCarloValidator
        mc = MonteCarloValidator(n_simulations=n_simulations)
        return mc.validate_sequencing(trades, n_simulations)

    async def _evaluate_gates(self, metrics: Dict, gates: List[Dict]) -> Dict:
        from analytics.validation.validation import ValidationGate, evaluate_gates
        gate_objs = [ValidationGate(**g) for g in gates]
        passed, failed, results = evaluate_gates(metrics, gate_objs)
        return {"passed": passed, "failed": failed}

    async def _evaluate_risk(self, signal: Dict, portfolio: Dict) -> Dict:
        from execution.engine import get_execution_engine
        engine = get_execution_engine()
        # Would convert dict to domain objects and evaluate
        return {"approved": True, "checks": {}}

    async def _check_limits(self, portfolio: Dict) -> Dict:
        return {"within_limits": True, "violations": []}

    async def _register_feature(self, name: str, formula: str, category: str,
                                source_data: List[str], lookback: int) -> Dict:
        from analytics.features import get_feature_registry, FeatureMetadata, FeatureCategory, NormalizationType
        registry = get_feature_registry()
        metadata = FeatureMetadata(
            name=name, category=category, formula=formula,
            source_data=source_data, lookback=lookback
        )
        registry.register(metadata)
        return {"status": "registered", "fingerprint": metadata.fingerprint}

    async def _check_leakage(self, features: List[Dict], labels: Optional[List[Dict]] = None) -> Dict:
        from analytics.leakage import get_leakage_sentinel
        import pandas as pd
        sentinel = get_leakage_sentinel()
        df = pd.DataFrame(features)
        labels_df = pd.DataFrame(labels) if labels else None
        results = sentinel.check_all(df, labels_df)
        return {
            "total_checks": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
        }

    async def _backtest_strategy(self, strategy_config: Dict, symbol: str,
                                 timeframe: str, start: str, end: str) -> Dict:
        return {"status": "completed", "metrics": {}}


def create_quant_mcp_server() -> QuantMCPServer:
    """Factory to create the quant MCP server."""
    return QuantMCPServer()