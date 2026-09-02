"""
Analytics package — Feature Factory, Feature Registry, Leakage Sentinel, Regime Detection.
"""
from __future__ import annotations

from analytics.features import (
    FeatureFactory,
    FeatureRegistry,
    FeatureMetadata,
    FeatureLineage,
)
from analytics.leakage import LeakageSentinel, LeakageCheckResult
from analytics.regime import RegimeDetector, RegimeType, RegimeState
from analytics.microfeatures import (
    derivative_features,
    options_iv_features,
    cross_asset_features,
    journal_features,
    event_features,
    compute_all as compute_microfeatures,
)

__all__ = [
    "FeatureFactory",
    "FeatureRegistry",
    "FeatureMetadata",
    "FeatureLineage",
    "LeakageSentinel",
    "LeakageCheckResult",
    "RegimeDetector",
    "RegimeType",
    "RegimeState",
    "derivative_features",
    "options_iv_features",
    "cross_asset_features",
    "journal_features",
    "event_features",
    "compute_microfeatures",
]