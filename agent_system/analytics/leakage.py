"""
Feature Leakage Sentinel — point-in-time safety checks for features.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd


class LeakageType(str, Enum):
    POINT_IN_TIME = "point_in_time"
    ROLLING_LEAKAGE = "rolling_leakage"
    FUTURE_OHLC = "future_ohlc"
    FUTURE_LABEL = "future_label"
    NORMALIZATION = "normalization"
    TRAIN_TEST_CONTAMINATION = "train_test_contamination"
    LOOKAHEAD_BIAS = "lookahead_bias"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class LeakageCheckResult:
    """Result of a leakage check."""
    check_name: str
    leakage_type: LeakageType
    severity: Severity
    passed: bool
    message: str
    details: Dict[str, Any] = None
    affected_features: List[str] = None
    affected_samples: int = 0

    def __post_init__(self):
        if self.details is None:
            self.details = {}
        if self.affected_features is None:
            self.affected_features = []


class LeakageSentinel:
    """
    Comprehensive leakage detection for feature engineering pipelines.
    Checks for point-in-time safety, rolling leakage, future OHLC access,
    label leakage, normalization leakage, and train/test contamination.
    """

    def __init__(
        self,
        lookback_window: int = 100,
        max_correlation_threshold: float = 0.95,
        contamination_threshold: float = 0.01,
    ):
        self.lookback_window = lookback_window
        self.max_correlation_threshold = max_correlation_threshold
        self.contamination_threshold = contamination_threshold

    def check_all(
        self,
        features_df: pd.DataFrame,
        labels_df: Optional[pd.DataFrame] = None,
        train_mask: Optional[pd.Series] = None,
        test_mask: Optional[pd.Series] = None,
    ) -> List[LeakageCheckResult]:
        """Run all leakage checks."""
        results = []

        results.extend(self._check_point_in_time(features_df))
        results.extend(self._check_rolling_leakage(features_df))
        results.extend(self._check_future_ohlc(features_df))
        results.extend(self._check_normalization_leakage(features_df))
        results.extend(self._check_correlation_leakage(features_df))

        if labels_df is not None:
            results.extend(self._check_label_leakage(features_df, labels_df))

        if train_mask is not None and test_mask is not None:
            results.extend(self._check_train_test_contamination(features_df, train_mask, test_mask))
            if labels_df is not None:
                results.extend(self._check_label_contamination(labels_df, train_mask, test_mask))

        return results

    def _check_point_in_time(self, df: pd.DataFrame) -> List[LeakageCheckResult]:
        """Check if features only use data available at prediction time."""
        results = []

        # Check for features that might use future data
        # This is a heuristic - in practice you'd track feature definitions
        # Look for features with suspiciously high correlation with future returns
        if "ret_1" in df.columns:
            for col in df.columns:
                if col in ("ret_1", "ret_5", "log_ret_1"):
                    continue
                # Check correlation with next period return
                corr = df[col].corr(df["ret_1"].shift(-1))
                if not np.isnan(corr) and abs(corr) > self.max_correlation_threshold:
                    results.append(LeakageCheckResult(
                        check_name=f"point_in_time_{col}",
                        leakage_type=LeakageType.POINT_IN_TIME,
                        severity=Severity.CRITICAL,
                        passed=False,
                        message=f"Feature '{col}' has {corr:.3f} correlation with next-period return",
                        details={"correlation": corr, "threshold": self.max_correlation_threshold},
                        affected_features=[col],
                    ))
        return results

    def _check_rolling_leakage(self, df: pd.DataFrame) -> List[LeakageCheckResult]:
        """Check for rolling window features that leak future info."""
        results = []

        # Features computed with rolling windows that might include future data
        # Check for features where the rolling window might be centered
        suspicious_patterns = ["rolling", "ewm", "expanding"]

        for col in df.columns:
            # Heuristic: if feature has extremely low variance or perfect autocorrelation
            # it might be a rolling stat computed with future data
            if df[col].nunique() < 5:
                continue

            # Check autocorrelation at lag 1
            autocorr = df[col].autocorr(lag=1)
            if not np.isnan(autocorr) and autocorr > 0.999:
                results.append(LeakageCheckResult(
                    check_name=f"rolling_leakage_{col}",
                    leakage_type=LeakageType.ROLLING_LEAKAGE,
                    severity=Severity.WARNING,
                    passed=False,
                    message=f"Feature '{col}' has suspiciously high autocorrelation ({autocorr:.4f})",
                    details={"autocorr": autocorr},
                    affected_features=[col],
                ))

        return results

    def _check_future_ohlc(self, df: pd.DataFrame) -> List[LeakageCheckResult]:
        """Check if features use future OHLC data."""
        results = []

        # Check for features that might use future high/low
        # e.g., features that use "high" but are computed at "open" time
        future_suspect_cols = [c for c in df.columns if any(
            kw in c.lower() for kw in ["high", "low", "max", "min", "range"]
        )]

        for col in future_suspect_cols:
            # Check if feature correlates with future high/low
            if "high" in df.columns and "low" in df.columns:
                corr_high = df[col].corr(df["high"].shift(-1))
                corr_low = df[col].corr(df["low"].shift(-1))
                if not np.isnan(corr_high) and abs(corr_high) > 0.5:
                    results.append(LeakageCheckResult(
                        check_name=f"future_ohlc_{col}",
                        leakage_type=LeakageType.FUTURE_OHLC,
                        severity=Severity.CRITICAL,
                        passed=False,
                        message=f"Feature '{col}' correlates with future high ({corr_high:.3f})",
                        details={"corr_high": corr_high},
                        affected_features=[col],
                    ))
                if not np.isnan(corr_low) and abs(corr_low) > 0.5:
                    results.append(LeakageCheckResult(
                        check_name=f"future_ohlc_{col}",
                        leakage_type=LeakageType.FUTURE_OHLC,
                        severity=Severity.CRITICAL,
                        passed=False,
                        message=f"Feature '{col}' correlates with future low ({corr_low:.3f})",
                        details={"corr_low": corr_low},
                        affected_features=[col],
                    ))
        return results

    def _check_normalization_leakage(self, df: pd.DataFrame) -> List[LeakageCheckResult]:
        """Check for normalization that uses future statistics."""
        results = []

        # Check for z-score normalization that might use future mean/std
        # If a feature has exactly mean=0, std=1 across the whole dataset,
        # it might have been normalized using future data
        for col in df.columns:
            if df[col].std() > 0:
                z_scores = (df[col] - df[col].mean()) / df[col].std()
                if z_scores.std() < 1e-10 and abs(z_scores.mean()) < 1e-10:
                    results.append(LeakageCheckResult(
                        check_name=f"normalization_{col}",
                        leakage_type=LeakageType.NORMALIZATION,
                        severity=Severity.WARNING,
                        passed=False,
                        message=f"Feature '{col}' appears globally normalized (mean={df[col].mean():.2e}, std={df[col].std():.2e})",
                        details={"mean": df[col].mean(), "std": df[col].std()},
                        affected_features=[col],
                    ))

        return results

    def _check_correlation_leakage(self, df: pd.DataFrame) -> List[LeakageCheckResult]:
        """Check for features that are essentially duplicates (high correlation)."""
        results = []

        numeric_cols = df.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) < 2:
            return results

        corr_matrix = df[numeric_cols].corr()
        for i, col1 in enumerate(numeric_cols):
            for col2 in numeric_cols[i+1:]:
                corr = corr_matrix.loc[col1, col2]
                if not np.isnan(corr) and abs(corr) > self.max_correlation_threshold:
                    results.append(LeakageCheckResult(
                        check_name=f"duplicate_features_{col1}_{col2}",
                        leakage_type=LeakageType.LOOKAHEAD_BIAS,
                        severity=Severity.WARNING,
                        passed=False,
                        message=f"Features '{col1}' and '{col2}' are highly correlated ({corr:.3f})",
                        details={"correlation": corr, "features": [col1, col2]},
                        affected_features=[col1, col2],
                    ))
        return results

    def _check_label_leakage(self, features_df: pd.DataFrame, labels_df: pd.DataFrame) -> List[LeakageCheckResult]:
        """Check if features leak label information."""
        results = []

        # Check correlation between features and future labels
        for label_col in labels_df.columns:
            for feat_col in features_df.columns:
                if feat_col in labels_df.columns:
                    continue
                corr = features_df[feat_col].corr(labels_df[label_col].shift(-1))
                if not np.isnan(corr) and abs(corr) > 0.3:  # Lower threshold for label leakage
                    results.append(LeakageCheckResult(
                        check_name=f"label_leakage_{feat_col}_{label_col}",
                        leakage_type=LeakageType.FUTURE_LABEL,
                        severity=Severity.CRITICAL,
                        passed=False,
                        message=f"Feature '{feat_col}' correlates with future label '{label_col}' ({corr:.3f})",
                        details={"correlation": corr, "label": label_col, "feature": feat_col},
                        affected_features=[feat_col],
                    ))
        return results

    def _check_train_test_contamination(
        self,
        df: pd.DataFrame,
        train_mask: pd.Series,
        test_mask: pd.Series,
    ) -> List[LeakageCheckResult]:
        """Check for train/test data contamination."""
        results = []

        if train_mask.sum() < 10 or test_mask.sum() < 10:
            return results

        train_df = df[train_mask]
        test_df = df[test_mask]

        # Check if test features' distributions differ significantly from train
        # (could indicate data leakage or regime change)
        from scipy import stats

        for col in df.select_dtypes(include=[np.number]).columns:
            train_vals = train_df[col].dropna()
            test_vals = test_df[col].dropna()
            if len(train_vals) > 10 and len(test_vals) > 10:
                # KS test for distribution similarity
                try:
                    ks_stat, p_value = stats.ks_2samp(train_vals, test_vals)
                    if p_value < self.contamination_threshold:
                        results.append(LeakageCheckResult(
                            check_name=f"train_test_contamination_{col}",
                            leakage_type=LeakageType.TRAIN_TEST_CONTAMINATION,
                            severity=Severity.WARNING,
                            passed=False,
                            message=f"Feature '{col}' has different distribution in train vs test (KS={ks_stat:.3f}, p={p_value:.3e})",
                            details={"ks_stat": ks_stat, "p_value": p_value},
                            affected_features=[col],
                        ))
                except Exception:
                    pass

        return results

    def _check_label_contamination(
        self,
        labels_df: pd.DataFrame,
        train_mask: pd.Series,
        test_mask: pd.Series,
    ) -> List[LeakageCheckResult]:
        """Check for label leakage between train/test."""
        results = []

        for label_col in labels_df.columns:
            train_labels = labels_df.loc[train_mask, label_col].dropna()
            test_labels = labels_df.loc[test_mask, label_col].dropna()

            if len(train_labels) > 10 and len(test_labels) > 10:
                from scipy import stats
                try:
                    ks_stat, p_value = stats.ks_2samp(train_labels, test_labels)
                    if p_value < self.contamination_threshold:
                        results.append(LeakageCheckResult(
                            check_name=f"label_contamination_{label_col}",
                            leakage_type=LeakageType.TRAIN_TEST_CONTAMINATION,
                            severity=Severity.CRITICAL,
                            passed=False,
                            message=f"Label '{label_col}' has different distribution in train vs test (KS={ks_stat:.3f}, p={p_value:.3e})",
                            details={"ks_stat": ks_stat, "p_value": p_value, "label": label_col},
                            affected_features=[label_col],
                        ))
                except Exception:
                    pass

        return results


# Global sentinel instance
_leakage_sentinel: Optional[LeakageSentinel] = None


def get_leakage_sentinel() -> LeakageSentinel:
    global _leakage_sentinel
    if _leakage_sentinel is None:
        _leakage_sentinel = LeakageSentinel()
    return _leakage_sentinel