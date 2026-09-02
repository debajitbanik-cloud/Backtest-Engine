"""
Alpha Computation — Information Coefficient, Information Ratio, Turnover, Stability,
Regime Dependency, and Orthogonality metrics for alpha factors.
"""
from __future__ import annotations

import asyncio
import math
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from analytics.validation.validation import evaluate_gates, ValidationGate, DEFAULT_GATES


def compute_information_coefficient(
    factor_returns: np.ndarray,
    future_returns: np.ndarray,
) -> float:
    """
    Compute Information Coefficient (IC) = correlation(factor, future_return).
    
    IC measures the linear relationship between a factor value and the subsequent
    asset return. Positive IC means higher factor values predict higher returns.
    """
    if len(factor_returns) != len(future_returns) or len(factor_returns) < 2:
        return 0.0

    # Remove NaN
    mask = ~np.isnan(factor_returns) & ~np.isnan(future_returns)
    f = factor_returns[mask]
    r = future_returns[mask]

    if len(f) < 2 or np.std(f) == 0 or np.std(r) == 0:
        return 0.0

    ic = np.corrcoef(f, r)[0, 1]
    return float(ic) if not np.isnan(ic) else 0.0


def compute_information_ratio(
    ics: np.ndarray,
) -> float:
    """
    Compute Information Ratio = mean(IC) / std(IC) * sqrt(N),
    
    where N is the number of trading days in a typical period.
    IR > 0.5 is considered decent, > 1.0 is excellent.
    """
    if len(ics) == 0:
        return 0.0

    ic_mean = np.mean(ics)
    ic_std = np.std(ics)

    if ic_std == 0:
        return 0.0

    # Annualized: assume 252 trading days, IC computed daily
    ir = (ic_mean / ic_std) * math.sqrt(252)
    return float(ir)


def compute_turnover(
    factor_values_previous: np.ndarray,
    factor_values_current: np.ndarray,
    turnover_threshold: float = 0.0,
) -> float:
    """
    Compute Portfolio Turnover = fraction of factor universe that changed
    sign or exceeded threshold between periods.
    
    Turnover > 0.5 (50%) is considered high, indicating frequent rebalancing.
    """
    if len(factor_values_previous) != len(factor_values_current) or len(factor_values_previous) == 0:
        return 0.0

    # Count changes in sign (long/short) or above/below threshold
    prev_sign = np.sign(factor_values_previous - turnover_threshold)
    curr_sign = np.sign(factor_values_current - turnover_threshold)

    # Handle zeros
    prev_sign[prev_sign == 0] = 1
    curr_sign[curr_sign == 0] = 1

    changes = prev_sign != curr_sign
    turnover = np.mean(changes)

    return float(turnover)


def compute_stability(
    ics: np.ndarray,
    window: int = 30,
) -> Dict[str, float]:
    """
    Compute Stability metrics over rolling windows.
    
    Returns:
        - rolling_ic_mean: mean IC over rolling windows
        - rolling_ic_std: std of IC over rolling windows
        - stability_score: 1 / (1 + rolling_ic_std) — higher is more stable
    """
    if len(ics) < window:
        return {
            "rolling_ic_mean": float(np.mean(ics)) if len(ics) > 0 else 0.0,
            "rolling_ic_std": float(np.std(ics)) if len(ics) > 0 else 0.0,
            "stability_score": 0.0,
        }

    rolling_means = []
    rolling_stds = []

    for i in range(window, len(ics) + 1):
        window_ics = ics[i - window : i]
        rolling_means.append(float(np.mean(window_ics)))
        rolling_stds.append(float(np.std(window_ics)))

    stability_score = 1.0 / (1.0 + np.mean(rolling_stds)) if rolling_stds else 0.0

    return {
        "rolling_ic_mean": float(np.mean(rolling_means)) if rolling_means else 0.0,
        "rolling_ic_std": float(np.mean(rolling_stds)) if rolling_stds else 0.0,
        "stability_score": float(stability_score),
    }


def compute_regime_dependency(
    factor_returns: np.ndarray,
    market_regimes: np.ndarray,
) -> Dict[str, float]:
    """
    Compute Regime Dependency: IC broken down by market regime.
    
    factor_returns: array of factor subsequent returns
    market_regimes: array of regime labels (0, 1, 2, ... matching known regimes)
    
    Returns IC per regime and regime exposure.
    """
    if len(factor_returns) != len(market_regimes) or len(factor_returns) == 0:
        return {}

    unique_regimes = np.unique(market_regimes)
    regime_ics = {}

    for regime in unique_regimes:
        mask = market_regimes == regime
        regime_ics[int(regime)] = float(
            np.corrcoef(factor_returns[mask], np.ones(len(factor_returns[mask])))[0, 1]
            if np.sum(mask) > 1
            else 0.0
        )

    # Also compute concentration: fraction of IC from largest regime
    if regime_ics:
        regime_values = np.array(list(regime_ics.values()))
        total_ic = np.sum(np.abs(regime_values))
        if total_ic > 0:
            dominant_regime_share = float(np.max(np.abs(regime_values)) / total_ic)
        else:
            dominant_regime_share = 0.0
    else:
        dominant_regime_share = 0.0

    return {
        "regime_ics": regime_ics,
        "dominant_regime_share": dominant_regime_share,
        "num_regimes": len(unique_regimes),
    }


def compute_orthogonality(
    factor1: np.ndarray,
    factor2: np.ndarray,
) -> float:
    """
    Compute Orthogonality between two factors = |correlation|.
    
    Orthogonality close to 0 means factors are uncorrelated (good for diversification).
    Orthogonality close to 1 means factors are highly redundant.
    """
    if len(factor1) != len(factor2) or len(factor1) < 2:
        return 1.0

    mask = ~np.isnan(factor1) & ~np.isnan(factor2)
    f1 = factor1[mask]
    f2 = factor2[mask]

    if len(f1) < 2 or np.std(f1) == 0 or np.std(f2) == 0:
        return 1.0

    corr = float(np.corrcoef(f1, f2)[0, 1])
    return abs(corr) if not np.isnan(corr) else 1.0


def compute_alpha_metrics(
    factor_values: np.ndarray,
    subsequent_returns: np.ndarray,
    market_regimes: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    Compute comprehensive alpha metrics for a single factor.
    
    Returns dict with IC, IR, p-value, stability, and regime breakdown.
    """
# Compute IC series (rolling or point-to-point)
    if len(factor_values) != len(subsequent_returns):
        return {"error": "factor and return lengths mismatch"}

    ics = []
    for i in range(1, len(factor_values)):
        # IC[i] = correlation using factor values up to i with return at i
        # Use all available non-NaN factor values from 0 to i
        f_slice = factor_values[:i]
        r_val = subsequent_returns[i] if i < len(subsequent_returns) else subsequent_returns[-1]
        valid_mask = ~np.isnan(f_slice)
        n_valid = np.sum(valid_mask)
        if n_valid > 1:
            # Need at least 2 factor values for correlation
            # Pair each factor value with the same return r_val (simple IC)
            f_valid = f_slice[valid_mask]
            # Create an array of same return repeated for each valid factor
            r_array = np.full_like(f_valid, r_val, dtype=float)
            ic = float(np.corrcoef(f_valid, r_array)[0, 1])
            if not np.isnan(ic) and np.isfinite(ic):
                ics.append(ic)
            else:
                ics.append(0.0)
        else:
            ics.append(0.0)

    ics = np.array(ics) if ics else np.array([])

    metrics = {
        "ic_mean": float(np.mean(ics)) if len(ics) > 0 else 0.0,
        "ic_std": float(np.std(ics)) if len(ics) > 0 else 0.0,
        "ic_sharpe": compute_information_ratio(ics),
        "ic_turnover": compute_turnover(
            ics[:-1] if len(ics) > 1 else ic,
            ics[1:] if len(ics) > 1 else ic,
        ),
    }

    if market_regimes is not None and len(market_regimes) == len(ics):
        metrics["regime_dependency"] = compute_regime_dependency(ics, market_regimes)

    # Stability over last N periods
    if len(ics) > 30:
        metrics["stability"] = compute_stability(ics, window=30)
    else:
        metrics["stability"] = compute_stability(ics)

    return metrics


class AlphaZoo:
    """
    Alpha Zoo — ranks and stores alpha factors with full metadata.
    Supports factor selection based on IC, IR, turnover, stability, and regime compatibility.
    """

    def __init__(self, max_factors: int = 50):
        self.max_factors = max_factors
        self.factors: Dict[str, Dict] = {}
        self.ranking_history: List[Dict] = []

    def add_factor(
        self,
        name: str,
        factor_values: np.ndarray,
        subsequent_returns: np.ndarray,
        market_regimes: Optional[np.ndarray] = None,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Add a factor to the Alpha Zoo and compute its metrics."""
        metrics = compute_alpha_metrics(factor_values, subsequent_returns, market_regimes)

        self.factors[name] = {
            "metrics": metrics,
            "factor_values": factor_values.copy(),
            "subsequent_returns": subsequent_returns.copy(),
            "market_regimes": market_regimes.copy() if market_regimes is not None else None,
            "metadata": metadata or {},
            "added_at": datetime.utcnow(),
        }

        # Re-rank all factors
        self._re_rank()

    def _re_rank(self) -> None:
        """Re-rank all factors by Information Ratio (primary) and Stability (secondary)."""
        ranked = []
        for name, data in self.factors.items():
            metrics = data["metrics"]
            ic_mean = metrics.get("ic_mean", 0.0)
            stability = metrics.get("stability", {}).get("stability_score", 0.0)
            ic_turnover = metrics.get("ic_turnover", 1.0)

            # Primary sort: IR descending, then stability descending, then low turnover
            rank_score = ic_mean / (1.0 + ic_turnover) if ic_turnover > 0 else ic_mean
            ranked.append((name, rank_score, ic_mean, stability))

        # Sort: higher rank_score is better
        ranked.sort(key=lambda x: x[1], reverse=True)

        self.ranking_history.append(
            {name: {"rank_score": score} for name, score, _, _ in ranked}
        )

        # Keep only top max_factors
        self.ranked = [(name, score, ic, stab) for name, score, ic, stab in ranked[: self.max_factors]]

    def get_top_factors(self, n: int = 5) -> List[Tuple[str, Dict]]:
        """Get top N ranked factors with their metrics."""
        if not hasattr(self, "ranked"):
            return []
        return [
            (name, self.factors[name]["metrics"])
            for name, _, _, _ in self.ranked[:n]
        ]

    def get_factor_ic(self, name: str) -> Optional[float]:
        """Get the mean IC of a specific factor."""
        if name in self.factors:
            return self.factors[name]["metrics"].get("ic_mean", 0.0)
        return None

    def check_orthogonality(self, name1: str, name2: str) -> Optional[float]:
        """Check orthogonality (correlation) between two factors."""
        if name1 not in self.factors or name2 not in self.factors:
            return None
        return compute_orthogonality(
            self.factors[name1]["factor_values"],
            self.factors[name2]["factor_values"],
        )

    def export_ranking(self) -> Dict:
        """Export current ranking with all factor metadata."""
        return {
            "ranked_factors": [
                {
                    "name": name,
                    "metrics": data["metrics"],
                    "metadata": data["metadata"],
                }
                for name, data in self.factors.items()
            ],
            "top_5": self.get_top_factors(5),
            "ranking_history_len": len(self.ranking_history),
        }


# Default regime labels for crypto/crypto-equity mapping
REGIME_BULL = 0
REGIME_BEAR = 1
REGIME_SIDEWAYS = 2
REGIME_HIGH_VOL = 3
REGIME_LOW_VOL = 4


def assign_market_regime(
    returns: np.ndarray,
    vol_threshold: float = 0.02,
) -> np.ndarray:
    """
    Simple regime assignment based on return magnitude and volatility.
    """
    regimes = np.zeros(len(returns), dtype=int)
    rolling_vol = np.zeros(len(returns))

    for i in range(1, len(returns)):
        window = returns[max(0, i - 20) : i]
        if len(window) > 0:
            rolling_vol[i] = float(np.std(window))
        else:
            rolling_vol[i] = 0.0

    # Assign regimes
    for i in range(len(returns)):
        if abs(returns[i]) > vol_threshold * 2:
            regimes[i] = REGIME_BEAR if returns[i] < 0 else REGIME_BULL
        elif rolling_vol[i] > vol_threshold:
            regimes[i] = REGIME_HIGH_VOL
        else:
            regimes[i] = REGIME_SIDEWAYS if abs(returns[i]) < vol_threshold else REGIME_LOW_VOL

    return regimes