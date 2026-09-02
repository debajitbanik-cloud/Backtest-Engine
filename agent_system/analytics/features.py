"""
Feature Factory, Registry, and Lineage tracking.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from shared.domain import Instrument


class FeatureCategory(str, Enum):
    PRICE = "price"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    VOLUME = "volume"
    MICROSTRUCTURE = "microstructure"
    DERIVATIVES = "derivatives"
    REGIME = "regime"
    CROSS_ASSET = "cross_asset"
    TIME = "time"


class NormalizationType(str, Enum):
    NONE = "none"
    ZSCORE = "zscore"
    MINMAX = "minmax"
    ROBUST = "robust"
    LOG = "log"
    PCT_CHANGE = "pct_change"


@dataclass
class FeatureMetadata:
    """Complete metadata for a feature."""
    name: str
    category: FeatureCategory
    formula: str  # Human-readable formula
    source_data: List[str]  # Required input columns
    lookback: int  # Number of periods
    normalization: NormalizationType = NormalizationType.NONE
    normalization_params: Dict[str, Any] = field(default_factory=dict)
    availability_timestamp: str = "close"  # "open", "close", "next_open"
    description: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0.0"

    @property
    def fingerprint(self) -> str:
        """Unique fingerprint of the feature definition."""
        content = f"{self.name}:{self.formula}:{self.lookback}:{self.normalization}:{json.dumps(self.normalization_params, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class FeatureLineage:
    """Tracks lineage from model -> feature set -> feature version -> dataset snapshot -> raw source."""
    model_id: str
    feature_set_id: str
    feature_fingerprints: Dict[str, str]  # feature_name -> fingerprint
    dataset_snapshot_id: str
    raw_source_hashes: Dict[str, str]  # source_name -> hash
    created_at: datetime = field(default_factory=datetime.utcnow)


class FeatureRegistry:
    """
    Versioned feature registry with formula, source data, lookback,
    normalization, and availability timestamp tracking.
    """

    def __init__(self, registry_path: str = "data/feature_registry.db"):
        self.registry_path = Path(registry_path)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self._features: Dict[str, FeatureMetadata] = {}
        self._init_db()

    def _init_db(self) -> None:
        import sqlite3
        with sqlite3.connect(self.registry_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS features (
                    name TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    formula TEXT NOT NULL,
                    source_data TEXT NOT NULL,
                    lookback INTEGER NOT NULL,
                    normalization TEXT NOT NULL,
                    normalization_params TEXT NOT NULL,
                    availability_timestamp TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    version TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feature_lineage (
                    id TEXT PRIMARY KEY,
                    model_id TEXT NOT NULL,
                    feature_set_id TEXT NOT NULL,
                    feature_fingerprints TEXT NOT NULL,
                    dataset_snapshot_id TEXT NOT NULL,
                    raw_source_hashes TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

    def register(self, feature: FeatureMetadata) -> FeatureMetadata:
        import sqlite3
        with sqlite3.connect(self.registry_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO features
                (name, category, formula, source_data, lookback, normalization,
                 normalization_params, availability_timestamp, description, tags,
                 version, fingerprint, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feature.name,
                    feature.category.value,
                    feature.formula,
                    json.dumps(feature.source_data),
                    feature.lookback,
                    feature.normalization.value,
                    json.dumps(feature.normalization_params),
                    feature.availability_timestamp,
                    feature.description,
                    json.dumps(feature.tags),
                    feature.version,
                    feature.fingerprint,
                    feature.created_at.isoformat(),
                ),
            )
        self._features[feature.name] = feature
        return feature

    def get(self, name: str) -> Optional[FeatureMetadata]:
        import sqlite3
        with sqlite3.connect(self.registry_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM features WHERE name = ?", (name,)).fetchone()
        if row:
            return self._row_to_feature(row)
        return None

    def list(self, category: Optional[FeatureCategory] = None) -> List[FeatureMetadata]:
        import sqlite3
        with sqlite3.connect(self.registry_path) as conn:
            conn.row_factory = sqlite3.Row
            if category:
                rows = conn.execute(
                    "SELECT * FROM features WHERE category = ? ORDER BY name",
                    (category.value,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM features ORDER BY category, name").fetchall()
        return [self._row_to_feature(r) for r in rows]

    def record_lineage(self, lineage: FeatureLineage) -> None:
        import sqlite3
        with sqlite3.connect(self.registry_path) as conn:
            conn.execute(
                """
                INSERT INTO feature_lineage
                (id, model_id, feature_set_id, feature_fingerprints,
                 dataset_snapshot_id, raw_source_hashes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(hash(f"{lineage.model_id}{lineage.feature_set_id}{lineage.created_at}")),
                    lineage.model_id,
                    lineage.feature_set_id,
                    json.dumps(lineage.feature_fingerprints),
                    lineage.dataset_snapshot_id,
                    json.dumps(lineage.raw_source_hashes),
                    lineage.created_at.isoformat(),
                ),
            )

    def _row_to_feature(self, row) -> FeatureMetadata:
        return FeatureMetadata(
            name=row["name"],
            category=FeatureCategory(row["category"]),
            formula=row["formula"],
            source_data=json.loads(row["source_data"]),
            lookback=row["lookback"],
            normalization=NormalizationType(row["normalization"]),
            normalization_params=json.loads(row["normalization_params"]),
            availability_timestamp=row["availability_timestamp"],
            description=row["description"],
            tags=json.loads(row["tags"]),
            version=row["version"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )


class FeatureFactory:
    """
    Computes features from raw market data.
    Provides a library of standard features across all categories.
    """

    def __init__(self, registry: Optional[FeatureRegistry] = None):
        self.registry = registry or FeatureRegistry()
        self._feature_fns: Dict[str, Callable[[pd.DataFrame], pd.Series]] = {}
        self._register_builtin_features()

    def _register_builtin_features(self) -> None:
        """Register all built-in feature computations."""
        # Price features
        self.register("close", lambda df: df["close"], FeatureCategory.PRICE,
                     "Close price", ["close"], 1)
        self.register("open", lambda df: df["open"], FeatureCategory.PRICE,
                     "Open price", ["open"], 1)
        self.register("high", lambda df: df["high"], FeatureCategory.PRICE,
                     "High price", ["high"], 1)
        self.register("low", lambda df: df["low"], FeatureCategory.PRICE,
                     "Low price", ["low"], 1)
        self.register("mid_price", lambda df: (df["high"] + df["low"]) / 2, FeatureCategory.PRICE,
                     "(High + Low) / 2", ["high", "low"], 1)
        self.register("typical_price", lambda df: (df["high"] + df["low"] + df["close"]) / 3, FeatureCategory.PRICE,
                     "(High + Low + Close) / 3", ["high", "low", "close"], 1)
        self.register("vwap", lambda df: (df["close"] * df["volume"]).cumsum() / df["volume"].cumsum()
                     if "volume" in df.columns else df["close"], FeatureCategory.PRICE,
                     "Volume-weighted average price", ["close", "volume"], 1)

        # Returns
        self.register("ret_1", lambda df: df["close"].pct_change(), FeatureCategory.PRICE,
                     "1-period return", ["close"], 2)
        self.register("ret_5", lambda df: df["close"].pct_change(5), FeatureCategory.PRICE,
                     "5-period return", ["close"], 6)
        self.register("log_ret_1", lambda df: np.log(df["close"] / df["close"].shift(1)), FeatureCategory.PRICE,
                     "1-period log return", ["close"], 2)

        # Momentum
        self.register("rsi_14", self._rsi(14), FeatureCategory.MOMENTUM,
                     "RSI(14)", ["close"], 15)
        self.register("rsi_7", self._rsi(7), FeatureCategory.MOMENTUM,
                     "RSI(7)", ["close"], 8)
        self.register("macd", self._macd(), FeatureCategory.MOMENTUM,
                     "MACD(12,26,9)", ["close"], 35)
        self.register("stoch_k", self._stoch_k(14), FeatureCategory.MOMENTUM,
                     "Stochastic %K(14)", ["high", "low", "close"], 15)
        self.register("stoch_d", self._stoch_d(14), FeatureCategory.MOMENTUM,
                     "Stochastic %D(14)", ["high", "low", "close"], 18)

        # Volatility
        self.register("atr_14", self._atr(14), FeatureCategory.VOLATILITY,
                     "ATR(14)", ["high", "low", "close"], 15)
        self.register("atr_7", self._atr(7), FeatureCategory.VOLATILITY,
                     "ATR(7)", ["high", "low", "close"], 8)
        self.register("bb_width", self._bb_width(20), FeatureCategory.VOLATILITY,
                     "Bollinger Band width(20)", ["close"], 21)
        self.register("bb_position", self._bb_position(20), FeatureCategory.VOLATILITY,
                     "Bollinger Band position(20)", ["close"], 21)
        self.register("realized_vol_20", lambda df: df["close"].pct_change().rolling(20).std() * np.sqrt(252),
                     FeatureCategory.VOLATILITY, "Annualized realized vol(20)", ["close"], 21)

        # Volume
        self.register("volume", lambda df: df["volume"] if "volume" in df.columns else 1, FeatureCategory.VOLUME,
                     "Volume", ["volume"], 1)
        self.register("volume_sma_20", lambda df: df["volume"].rolling(20).mean() if "volume" in df.columns else 1,
                     FeatureCategory.VOLUME, "Volume SMA(20)", ["volume"], 21)
        self.register("volume_ratio", lambda df: df["volume"] / df["volume"].rolling(20).mean()
                     if "volume" in df.columns else 1, FeatureCategory.VOLUME,
                     "Volume / Volume SMA(20)", ["volume"], 21)

        # Microstructure
        self.register("spread", lambda df: df["high"] - df["low"], FeatureCategory.MICROSTRUCTURE,
                     "High-Low spread", ["high", "low"], 1)
        self.register("spread_pct", lambda df: (df["high"] - df["low"]) / df["close"],
                     FeatureCategory.MICROSTRUCTURE, "Spread %", ["high", "low", "close"], 1)

        # Time features
        self.register("hour", lambda df: pd.to_datetime(df.index).hour, FeatureCategory.TIME,
                     "Hour of day", [], 1, normalization=NormalizationType.NONE)
        self.register("day_of_week", lambda df: pd.to_datetime(df.index).dayofweek, FeatureCategory.TIME,
                     "Day of week (0=Mon)", [], 1, normalization=NormalizationType.NONE)
        self.register("is_weekend", lambda df: (pd.to_datetime(df.index).dayofweek >= 5).astype(int),
                     FeatureCategory.TIME, "Is weekend", [], 1, normalization=NormalizationType.NONE)

        # Cross-asset (placeholder - requires multiple instruments)
        self.register("corr_btc_eth", lambda df: 0.0, FeatureCategory.CROSS_ASSET,
                     "BTC-ETH correlation placeholder", [], 1)

    def register(
        self,
        name: str,
        fn: Callable[[pd.DataFrame], pd.Series],
        category: FeatureCategory,
        formula: str,
        source_data: List[str],
        lookback: int,
        normalization: NormalizationType = NormalizationType.NONE,
        normalization_params: Dict[str, Any] = None,
    ) -> None:
        """Register a feature computation function."""
        self._feature_fns[name] = fn
        metadata = FeatureMetadata(
            name=name,
            category=category,
            formula=formula,
            source_data=source_data,
            lookback=lookback,
            normalization=normalization,
            normalization_params=normalization_params or {},
        )
        self.registry.register(metadata)

    def compute(self, df: pd.DataFrame, features: List[str]) -> pd.DataFrame:
        """Compute requested features for a DataFrame."""
        result = df.copy()
        for name in features:
            if name in self._feature_fns:
                try:
                    result[name] = self._feature_fns[name](df)
                except Exception as e:
                    print(f"Feature {name} computation failed: {e}")
                    result[name] = np.nan
            else:
                print(f"Unknown feature: {name}")
                result[name] = np.nan
        return result

    def compute_all(self, df: pd.DataFrame, categories: Optional[List[str]] = None) -> pd.DataFrame:
        """Compute all registered features (or filtered by category)."""
        features = list(self._feature_fns.keys())
        if categories:
            cats = [FeatureCategory(c) for c in categories]
            features = [f for f in features if self.registry.get(f) and self.registry.get(f).category in cats]
        return self.compute(df, features)

    # ── Built-in feature implementations ──────────────────────────────────

    def _rsi(self, period: int) -> Callable[[pd.DataFrame], pd.Series]:
        def _calc(df: pd.DataFrame) -> pd.Series:
            delta = df["close"].diff()
            gain = delta.clip(lower=0).rolling(period).mean()
            loss = (-delta.clip(upper=0)).rolling(period).mean()
            rs = gain / loss.replace(0, np.nan)
            return 100 - (100 / (1 + rs))
        return _calc

    def _macd(self) -> Callable[[pd.DataFrame], pd.Series]:
        def _calc(df: pd.DataFrame) -> pd.Series:
            ema12 = df["close"].ewm(span=12, adjust=False).mean()
            ema26 = df["close"].ewm(span=26, adjust=False).mean()
            return ema12 - ema26
        return _calc

    def _stoch_k(self, period: int) -> Callable[[pd.DataFrame], pd.Series]:
        def _calc(df: pd.DataFrame) -> pd.Series:
            low_min = df["low"].rolling(period).min()
            high_max = df["high"].rolling(period).max()
            return 100 * (df["close"] - low_min) / (high_max - low_min).replace(0, np.nan)
        return _calc

    def _stoch_d(self, period: int) -> Callable[[pd.DataFrame], pd.Series]:
        def _calc(df: pd.DataFrame) -> pd.Series:
            low_min = df["low"].rolling(period).min()
            high_max = df["high"].rolling(period).max()
            k = 100 * (df["close"] - low_min) / (high_max - low_min).replace(0, np.nan)
            return k.rolling(3).mean()
        return _calc

    def _atr(self, period: int) -> Callable[[pd.DataFrame], pd.Series]:
        def _calc(df: pd.DataFrame) -> pd.Series:
            high_low = df["high"] - df["low"]
            high_close = (df["high"] - df["close"].shift()).abs()
            low_close = (df["low"] - df["close"].shift()).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            return tr.rolling(period).mean()
        return _calc

    def _bb_width(self, period: int) -> Callable[[pd.DataFrame], pd.Series]:
        def _calc(df: pd.DataFrame) -> pd.Series:
            sma = df["close"].rolling(period).mean()
            std = df["close"].rolling(period).std()
            upper = sma + 2 * std
            lower = sma - 2 * std
            return (upper - lower) / sma.replace(0, np.nan)
        return _calc

    def _bb_position(self, period: int) -> Callable[[pd.DataFrame], pd.Series]:
        def _calc(df: pd.DataFrame) -> pd.Series:
            sma = df["close"].rolling(period).mean()
            std = df["close"].rolling(period).std()
            upper = sma + 2 * std
            lower = sma - 2 * std
            return (df["close"] - lower) / (upper - lower).replace(0, np.nan)
        return _calc


# Global instances
_feature_factory: Optional[FeatureFactory] = None
_feature_registry: Optional[FeatureRegistry] = None


def get_feature_factory() -> FeatureFactory:
    global _feature_factory
    if _feature_factory is None:
        _feature_factory = FeatureFactory()
    return _feature_factory


def get_feature_registry() -> FeatureRegistry:
    global _feature_registry
    if _feature_registry is None:
        _feature_registry = FeatureRegistry()
    return _feature_registry