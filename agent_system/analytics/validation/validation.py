"""
Validation Plane — Walk-Forward Optimization, CPCV, Monte Carlo, Gates.
"""
from __future__ import annotations

import hashlib
import json
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from sklearn.model_selection import TimeSeriesSplit
from sklearn.base import clone


@dataclass
class ValidationResult:
    """Result of a validation run."""
    validation_type: str  # "walk_forward", "cpcv", "monte_carlo"
    strategy_id: str
    parameters: Dict[str, Any]
    start_date: str
    end_date: str
    n_folds: int
    n_samples: int
    metrics: Dict[str, float]  # aggregated metrics
    fold_metrics: List[Dict[str, float]]  # per-fold
    passed_gates: List[str]
    failed_gates: List[str]
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GateResult:
    """Result of a single validation gate."""
    gate_name: str
    passed: bool
    value: float
    threshold: float
    operator: str  # ">=", "<=", ">", "<"
    message: str


class ValidationGate:
    """
    Validation gate with threshold and comparison operator.
    """

    def __init__(
        self,
        name: str,
        metric: str,
        threshold: float,
        operator: str = ">=",
        description: str = "",
    ):
        self.name = name
        self.metric = metric
        self.threshold = threshold
        self.operator = operator
        self.description = description

    def evaluate(self, metrics: Dict[str, float]) -> GateResult:
        value = metrics.get(self.metric, None)
        if value is None:
            return GateResult(
                gate_name=self.name,
                passed=False,
                value=float("nan"),
                threshold=self.threshold,
                operator=self.operator,
                message=f"Metric '{self.metric}' not found in results",
            )

        passed = self._compare(value, self.threshold, self.operator)
        return GateResult(
            gate_name=self.name,
            passed=passed,
            value=value,
            threshold=self.threshold,
            operator=self.operator,
            message=f"{self.name}: {value:.4f} {self.operator} {self.threshold} -> {'PASS' if passed else 'FAIL'}",
        )

    def _compare(self, value: float, threshold: float, operator: str) -> bool:
        if operator == ">=":
            return value >= threshold
        elif operator == ">":
            return value > threshold
        elif operator == "<=":
            return value <= threshold
        elif operator == "<":
            return value < threshold
        elif operator == "==":
            return value == threshold
        else:
            raise ValueError(f"Unknown operator: {operator}")


# Default gate set
DEFAULT_GATES = [
    ValidationGate("min_trades", "trades", 30, ">=", "Minimum 30 trades"),
    ValidationGate("min_win_rate", "win_rate", 0.40, ">=", "Minimum 40% win rate"),
    ValidationGate("min_profit_factor", "profit_factor", 1.0, ">=", "Profit factor >= 1.0"),
    ValidationGate("max_drawdown", "max_drawdown_pct", 0.15, "<=", "Max drawdown <= 15%"),
    ValidationGate("min_sharpe", "sharpe_ratio", 0.5, ">=", "Sharpe ratio >= 0.5"),
    ValidationGate("min_expectancy", "expectancy", 0.0, ">=", "Positive expectancy"),
]


class WalkForwardOptimizer:
    """
    Walk-Forward Optimization with expanding or rolling windows.
    """

    def __init__(
        self,
        train_window: int = 252,  # trading days
        test_window: int = 63,    # ~quarter
        step: int = 21,           # ~month
        min_train_size: int = 100,
        expanding: bool = True,
    ):
        self.train_window = train_window
        self.test_window = test_window
        self.step = step
        self.min_train_size = min_train_size
        self.expanding = expanding

    def split(self, n_samples: int) -> List[Tuple[np.ndarray, np.ndarray]]:
        """Generate walk-forward train/test index splits."""
        splits = []
        start = 0

        while start + self.train_window + self.test_window <= n_samples:
            train_end = start + self.train_window
            test_end = train_end + self.test_window

            if not self.expanding:
                # Rolling window
                train_start = max(0, train_end - self.train_window)
            else:
                train_start = 0

            if train_end - train_start < self.min_train_size:
                start += self.step
                continue

            train_idx = np.arange(train_start, train_end)
            test_idx = np.arange(train_end, test_end)

            splits.append((train_idx, test_idx))
            start += self.step

        return splits

    def validate(
        self,
        model_factory: Callable[[], Any],
        X: np.ndarray,
        y: np.ndarray,
        gates: Optional[List[ValidationGate]] = None,
        metric_fn: Optional[Callable] = None,
        strategy_id: str = "unknown",
    ) -> ValidationResult:
        """
        Run walk-forward validation.

        Args:
            model_factory: Function returning a fresh model instance
            X: Features (n_samples, n_features)
            y: Targets (n_samples,)
            gates: Validation gates to apply
            metric_fn: Function(model, X_test, y_test) -> Dict[str, float]
            strategy_id: Strategy identifier
        """
        if gates is None:
            gates = DEFAULT_GATES

        n_samples = len(X)
        splits = self.split(n_samples)

        fold_metrics = []
        all_predictions = []
        all_actuals = []

        for fold_idx, (train_idx, test_idx) in enumerate(splits):
            model = model_factory()
            model.fit(X[train_idx], y[train_idx])

            if metric_fn:
                metrics = metric_fn(model, X[test_idx], y[test_idx])
            else:
                # Default: accuracy for classification, R2 for regression
                preds = model.predict(X[test_idx])
                if len(np.unique(y)) <= 10:
                    from sklearn.metrics import accuracy_score
                    metrics = {"accuracy": accuracy_score(y[test_idx], preds)}
                else:
                    from sklearn.metrics import r2_score, mean_squared_error
                    metrics = {
                        "r2": r2_score(y[test_idx], preds),
                        "mse": mean_squared_error(y[test_idx], preds),
                    }

            fold_metrics.append(metrics)
            all_predictions.extend(model.predict(X[test_idx]))
            all_actuals.extend(y[test_idx])

        # Aggregate metrics
        agg_metrics = {}
        if fold_metrics:
            for key in fold_metrics[0].keys():
                values = [fm.get(key, 0) for fm in fold_metrics]
                agg_metrics[key] = np.mean(values)
                agg_metrics[f"{key}_std"] = np.std(values)

        # Evaluate gates
        gates_to_use = gates or DEFAULT_GATES
        passed_gates = []
        failed_gates = []
        for gate in gates_to_use:
            result = gate.evaluate(agg_metrics)
            if result.passed:
                passed_gates.append(gate.name)
            else:
                failed_gates.append(gate.name)

        return ValidationResult(
            validation_type="walk_forward",
            strategy_id=strategy_id,
            parameters={},  # would be filled by caller
            start_date="",
            end_date="",
            n_folds=len(splits),
            n_samples=n_samples,
            metrics=agg_metrics,
            fold_metrics=fold_metrics,
            passed_gates=passed_gates,
            failed_gates=failed_gates,
        )


class CombinatorialPurgedCV:
    """
    Combinatorial Purged Cross-Validation (CPCV) for time series.
    Based on López de Prado's "Advances in Financial Machine Learning".
    """

    def __init__(
        self,
        n_splits: int = 5,
        n_test_splits: int = 2,
        purge_pct: float = 0.01,
        embargo_pct: float = 0.01,
    ):
        self.n_splits = n_splits
        self.n_test_splits = n_test_splits
        self.purge_pct = purge_pct
        self.embargo_pct = embargo_pct

    def split(self, n_samples: int) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        Generate CPCV splits with purging and embargo.
        """
        # Create base time series splits
        tscv = TimeSeriesSplit(n_splits=self.n_splits)
        base_splits = list(tscv.split(np.arange(n_samples)))

        purged_embargoed = []

        for train_idx, test_idx in base_splits:
            # Apply purging: remove samples near test set from training
            purge_size = int(len(test_idx) * self.purge_pct)
            embargo_size = int(len(test_idx) * self.embargo_pct)

            # Purge: remove samples around test boundaries
            train_start = train_idx[0]
            train_end = train_idx[-1]
            test_start = test_idx[0]
            test_end = test_idx[-1]

            # Remove purge_size samples before test_start and after test_end
            purge_start = max(0, test_start - purge_size)
            purge_end = min(n_samples - 1, test_end + purge_size)

            # Embargo: additional gap after test
            embargo_end = min(n_samples - 1, test_end + embargo_size)

            # Filter training indices
            purged_train = train_idx[
                (train_idx < purge_start) | (train_idx > purge_end)
            ]

            # Also remove embargo period
            if embargo_end > purge_end:
                purged_train = purged_train[purged_train <= embargo_end]

            if len(purged_train) > 10 and len(test_idx) > 5:
                purged_embargoed.append((purged_train, test_idx))

        return purged_embargoed

    def validate(
        self,
        model_factory: Callable[[], Any],
        X: np.ndarray,
        y: np.ndarray,
        gates: Optional[List[ValidationGate]] = None,
        metric_fn: Optional[Callable] = None,
        strategy_id: str = "unknown",
    ) -> ValidationResult:
        """Run CPCV validation."""
        if gates is None:
            gates = DEFAULT_GATES

        n_samples = len(X)
        splits = self.split(n_samples)

        fold_metrics = []

        for fold_idx, (train_idx, test_idx) in enumerate(splits):
            model = model_factory()
            model.fit(X[train_idx], y[train_idx])

            if metric_fn:
                metrics = metric_fn(model, X[test_idx], y[test_idx])
            else:
                preds = model.predict(X[test_idx])
                if len(np.unique(y)) <= 10:
                    from sklearn.metrics import accuracy_score
                    metrics = {"accuracy": accuracy_score(y[test_idx], preds)}
                else:
                    from sklearn.metrics import r2_score, mean_squared_error
                    metrics = {
                        "r2": r2_score(y[test_idx], preds),
                        "mse": mean_squared_error(y[test_idx], preds),
                    }

            fold_metrics.append(metrics)

        # Aggregate
        agg_metrics = {}
        if fold_metrics:
            for key in fold_metrics[0].keys():
                values = [fm.get(key, 0) for fm in fold_metrics]
                agg_metrics[key] = np.mean(values)
                agg_metrics[f"{key}_std"] = np.std(values)

        # Gates
        gates_to_use = gates or DEFAULT_GATES
        passed_gates = []
        failed_gates = []
        for gate in gates_to_use:
            result = gate.evaluate(agg_metrics)
            if result.passed:
                passed_gates.append(gate.name)
            else:
                failed_gates.append(gate.name)

        return ValidationResult(
            validation_type="cpcv",
            strategy_id=strategy_id,
            parameters={},
            start_date="",
            end_date="",
            n_folds=len(splits),
            n_samples=n_samples,
            metrics=agg_metrics,
            fold_metrics=fold_metrics,
            passed_gates=passed_gates,
            failed_gates=failed_gates,
        )


class MonteCarloValidator:
    """
    Monte Carlo validation for trade sequencing and parameter perturbation.
    """

    def __init__(
        self,
        n_simulations: int = 1000,
        perturbation_pct: float = 0.1,
        sequence_method: str = "bootstrap",  # "bootstrap", "permutation"
    ):
        self.n_simulations = n_simulations
        self.perturbation_pct = perturbation_pct
        self.sequence_method = sequence_method

    def validate_sequencing(
        self,
        trades: List[Dict[str, Any]],
        n_simulations: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Monte Carlo trade sequencing test.
        Resamples trade sequence to estimate distribution of outcomes.
        """
        n = n_simulations or self.n_simulations
        if len(trades) < 10:
            return {"error": "Need at least 10 trades"}

        pnls = [t.get("pnl", 0) for t in trades]

        results = {
            "original_pnl": sum(pnls),
            "simulated_pnls": [],
            "drawdowns": [],
            "max_drawdowns": [],
        }

        for _ in range(n):
            if self.sequence_method == "bootstrap":
                sample = np.random.choice(pnls, size=len(pnls), replace=True)
            else:
                sample = np.random.permutation(pnls)

            cum_pnl = np.cumsum(sample)
            results["simulated_pnls"].append(cum_pnl[-1])

            # Drawdown
            peak = np.maximum.accumulate(cum_pnl)
            dd = peak - cum_pnl
            results["drawdowns"].append(dd)
            results["max_drawdowns"].append(np.max(dd))

        # Statistics
        sim_pnls = np.array(results["simulated_pnls"])
        results["mean_pnl"] = float(np.mean(sim_pnls))
        results["std_pnl"] = float(np.std(sim_pnls))
        results["pct_positive"] = float(np.mean(sim_pnls > 0))
        results["var_95"] = float(np.percentile(sim_pnls, 5))
        results["expected_shortfall"] = float(np.mean(sim_pnls[sim_pnls <= np.percentile(sim_pnls, 5)]))

        max_dds = np.array(results["max_drawdowns"])
        results["mean_max_drawdown"] = float(np.mean(max_dds))
        results["max_max_drawdown"] = float(np.max(max_dds))

        return results

    def validate_parameter_stability(
        self,
        backtest_fn: Callable[[Dict[str, Any]], Dict[str, float]],
        base_params: Dict[str, Any],
        param_ranges: Dict[str, Tuple[float, float]],
        n_simulations: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Monte Carlo parameter perturbation test.
        Perturbs parameters within ranges to test strategy robustness.
        """
        n = n_simulations or self.n_simulations
        results = {
            "base_metrics": backtest_fn(base_params),
            "perturbed_results": [],
        }

        for _ in range(n):
            perturbed = {}
            for key, value in base_params.items():
                if key in param_ranges:
                    low, high = param_ranges[key]
                    if isinstance(value, int):
                        perturbed[key] = np.random.randint(low, high + 1)
                    else:
                        perturbed[key] = np.random.uniform(low, high)
                else:
                    perturbed[key] = value

            try:
                metrics = backtest_fn(perturbed)
                results["perturbed_results"].append({
                    "params": perturbed,
                    "metrics": metrics,
                })
            except Exception as e:
                results["perturbed_results"].append({
                    "params": perturbed,
                    "error": str(e),
                })

        # Analyze stability
        successful = [r for r in results["perturbed_results"] if "error" not in r]
        if successful:
            for metric in results["base_metrics"]:
                values = [r["metrics"].get(metric, 0) for r in successful if metric in r["metrics"]]
                if values:
                    results[f"{metric}_stability"] = {
                        "mean": np.mean(values),
                        "std": np.std(values),
                        "min": np.min(values),
                        "max": np.max(values),
                        "cv": np.std(values) / (np.mean(values) + 1e-10),
                    }

        return results


# ── Gate evaluation utilities ───────────────────────────────────────────────

def evaluate_gates(
    metrics: Dict[str, float],
    gates: Optional[List[ValidationGate]] = None,
) -> Tuple[List[str], List[str], List[GateResult]]:
    """Evaluate all gates against metrics."""
    gates_to_use = gates or DEFAULT_GATES
    passed = []
    failed = []
    results = []

    for gate in gates_to_use:
        result = gate.evaluate(metrics)
        results.append(result)
        if result.passed:
            passed.append(gate.name)
        else:
            failed.append(gate.name)

    return passed, failed, results


def auto_reject(
    validation_result: ValidationResult,
    require_all_gates: bool = True,
) -> bool:
    """
    Determine if a research artifact should be automatically rejected.
    Returns True if rejected, False if accepted.
    """
    if require_all_gates:
        return len(validation_result.failed_gates) > 0
    else:
        # Reject if critical gates fail
        critical_gates = {"min_trades", "min_profit_factor", "max_drawdown"}
        return bool(set(validation_result.failed_gates) & critical_gates)