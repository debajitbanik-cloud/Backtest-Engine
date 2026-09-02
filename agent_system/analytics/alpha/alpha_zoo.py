"""
Alpha Zoo — factor registry, ranking, and selection.

Manages alpha factor lifecycle: registration, IC/IR computation,
ranking by quality metrics, orthogonality checks, and regime-aware
selection for portfolio construction.
"""
from __future__ import annotations

import numpy as np
from datetime import datetime
from typing import Any, Dict, List, Optional

from analytics.alpha.alpha_compute import (
    AlphaZoo as BaseAlphaZoo,
    compute_alpha_metrics,
    compute_orthogonality,
    assign_market_regime,
)


class AlphaZoo(BaseAlphaZoo):
    """
    Extended Alpha Zoo with additional selection gates and
    integration with the validation framework.
    """

    def __init__(self, max_factors: int = 50, ic_threshold: float = 0.02, ir_threshold: float = 0.5):
        super().__init__(max_factors=max_factors)
        self.ic_threshold = ic_threshold
        self.ir_threshold = ir_threshold
        self._orthogonality_matrix: Optional[np.ndarray] = None
        self._factor_names: List[str] = []

    def add_factor(
        self,
        name: str,
        factor_values: np.ndarray,
        subsequent_returns: np.ndarray,
        market_regimes: Optional[np.ndarray] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Add a factor and return selection decision.
        
        Returns dict with pass/fail reasons based on gates.
        """
        # Compute metrics
        metrics = compute_alpha_metrics(factor_values, subsequent_returns, market_regimes)

        # Apply selection gates
        gates_pass, gate_results = self._check_gates(metrics)

        if not gates_pass:
            return {
                "name": name,
                "accepted": False,
                "reasons": [r for r, p in gate_results if not p],
                "metrics": metrics,
            }

        # Call parent add_factor (which ranks)
        super().add_factor(name, factor_values, subsequent_returns, market_regimes, metadata)

        return {
            "name": name,
            "accepted": True,
            "rank": self._get_rank(name),
            "metrics": metrics,
        }

    def _check_gates(
        self, metrics: Dict[str, Any]
    ) -> Tuple[bool, List[Tuple[str, bool]]]:
        """Check factor against validation gates."""
        results = []

        # IC must be above threshold
        ic_mean = metrics.get("ic_mean", 0.0)
        ic_sharpe = metrics.get("ic_sharpe", 0.0)
        results.append(("IC_mean >= threshold", ic_mean >= self.ic_threshold))
        results.append(("IR >= threshold", ic_sharpe >= self.ir_threshold))

        # Turnover must not be excessive
        ic_turnover = metrics.get("ic_turnover", 1.0)
        results.append(("Turnover < 0.5", ic_turnover < 0.5))

        # Stability must be reasonable
        stability = metrics.get("stability", {}).get("stability_score", 0.0)
        results.append(("Stability > 0.3", stability > 0.3))

        # IC consistency (low std)
        ic_std = metrics.get("ic_std", 1.0)
        results.append(("IC std < 0.5", ic_std < 0.5))

        passed = all(p for _, p in results)
        return passed, results

    def _get_rank(self, name: str) -> Optional[int]:
        """Get the rank of a specific factor."""
        if not hasattr(self, "ranked"):
            return None
        for i, (n, _, _, _) in enumerate(self.ranked):
            if n == name:
                return i + 1
        return None

    def check_pairwise_orthogonality(
        self, name1: str, name2: str,
    ) -> Optional[float]:
        """
        Check orthogonality between two factors.
        Returns correlation absolute value; < 0.3 is considered orthogonal.
        """
        return compute_orthogonality(
            self.factors[name1]["factor_values"],
            self.factors[name2]["factor_values"],
        )

    def select_factors_by_regime(
        self, target_regime: int, exclude_names: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Select factors that performed best in a specific market regime.
        """
        if exclude_names is None:
            exclude_names = []

        selected = []
        for name, data in self.factors.items():
            if name in exclude_names:
                continue
            regimes = data.get("market_regimes")
            if regimes is None:
                continue

            # Compute IC in target regime
            mask = regimes == target_regime
            if np.sum(mask) == 0:
                continue

            # Simple: check if factor has positive IC in this regime
            factor_vals = data["factor_values"][mask]
            returns = data["subsequent_returns"][mask] if len(data["subsequent_returns"]) > 0 else np.array([])
            if len(factor_vals) > 1 and len(returns) > 0:
                ic = float(np.corrcoef(factor_vals, returns[:len(factor_vals)])[0, 1])
                if not np.isnan(ic) and ic > 0:
                    selected.append(name)

        # Re-rank selected by IC in target regime
        selected_ics = []
        for name in selected:
            regimes = self.factors[name]["market_regimes"]
            mask = regimes == target_regime
            factor_vals = self.factors[name]["factor_values"][mask]
            returns = self.factors[name]["subsequent_returns"][mask] if len(self.factors[name]["subsequent_returns"]) > 0 else np.array([])
            if len(factor_vals) > 1 and len(returns) > 0:
                ic = float(np.corrcoef(factor_vals, returns[:len(factor_vals)])[0, 1])
                ic_mean = ic if not np.isnan(ic) else 0.0
                selected_ics.append((name, ic_mean))

        selected_ics.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in selected_ics]

    def export_full_report(self) -> Dict:
        """Export comprehensive Alpha Zoo report."""
        base_report = super().export_ranking()
        base_report["selection_gates"] = {
            "ic_threshold": self.ic_threshold,
            "ir_threshold": self.ir_threshold,
        }
        base_report["orthogonality_matrix_ready"] = self._factor_names is not None
        return base_report