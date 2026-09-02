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


def _normalize_series(
    s: pd.Series,
    norm: NormalizationType,
    params: Optional[Dict[str, Any]] = None,
) -> pd.Series:
    """Apply a registered normalization transform to a feature series.

    Returns a copy so the raw feature value is never mutated in place. NaN values
    are preserved throughout. For ZSCORE/ROBUST/MINMAX the statistics are computed
    over the full series (production uses a fit-transform split; here we expose the
    transform for feature exploration).
    """
    params = params or {}
    out = s
    if norm == NormalizationType.ZSCORE:
        mu = float(params.get("mean", np.nanmean(s)))
        sd = float(params.get("std", np.nanstd(s)))
        out = (s - mu) / sd if sd and sd > 0 else s * np.nan
    elif norm == NormalizationType.MINMAX:
        lo = float(params.get("min", np.nanmin(s)))
        hi = float(params.get("max", np.nanmax(s)))
        out = (s - lo) / (hi - lo) if hi and hi > lo else s * np.nan
    elif norm == NormalizationType.ROBUST:
        med = float(params.get("median", np.nanmedian(s)))
        iqr = float(params.get("iqr", np.nanpercentile(s, 75) - np.nanpercentile(s, 25)))
        out = (s - med) / iqr if iqr and iqr > 0 else s * np.nan
    elif norm == NormalizationType.LOG:
        out = np.log(np.where(s > 0, s, np.nan))
    elif norm == NormalizationType.PCT_CHANGE:
        out = s.pct_change()
    return pd.Series(out, index=s.index, name=s.name)


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

        # ── Extended momentum / trend features ──────────────────────────────
        self.register("ema9", lambda df: df["close"].ewm(span=9, adjust=False).mean(), FeatureCategory.PRICE,
                     "EMA(9)", ["close"], 10)
        self.register("ema21", lambda df: df["close"].ewm(span=21, adjust=False).mean(), FeatureCategory.PRICE,
                     "EMA(21)", ["close"], 22)
        self.register("ema50", lambda df: df["close"].ewm(span=50, adjust=False).mean(), FeatureCategory.PRICE,
                     "EMA(50)", ["close"], 51)
        self.register("sma20", lambda df: df["close"].rolling(20).mean(), FeatureCategory.PRICE,
                     "SMA(20)", ["close"], 21)
        self.register("sma50", lambda df: df["close"].rolling(50).mean(), FeatureCategory.PRICE,
                     "SMA(50)", ["close"], 51)
        self.register("sma200", lambda df: df["close"].rolling(200).mean(), FeatureCategory.PRICE,
                     "SMA(200)", ["close"], 201)
        self.register("price_dist_sma50", lambda df: (df["close"] / df["close"].rolling(50).mean() - 1) * 100,
                     FeatureCategory.MOMENTUM, "Price distance from SMA(50) %", ["close"], 51)
        self.register("price_dist_sma200", lambda df: (df["close"] / df["close"].rolling(200).mean() - 1) * 100,
                     FeatureCategory.MOMENTUM, "Price distance from SMA(200) %", ["close"], 201)
        self.register("ema_fast_slow", lambda df: df["close"].ewm(span=12, adjust=False).mean() - df["close"].ewm(span=26, adjust=False).mean(),
                     FeatureCategory.MOMENTUM, "EMA(12)-EMA(26) distance", ["close"], 27)
        self.register("macd_histogram", self._macd_hist(), FeatureCategory.MOMENTUM,
                     "MACD histogram", ["close"], 35)
        self.register("macd_signal", lambda df: df["close"].ewm(span=12, adjust=False).mean().sub(
            df["close"].ewm(span=26, adjust=False).mean()).ewm(span=9, adjust=False).mean(),
            FeatureCategory.MOMENTUM, "MACD signal line", ["close"], 35)
        self.register("roc_10", lambda df: df["close"].pct_change(10) * 100, FeatureCategory.MOMENTUM,
                     "ROC(10) %", ["close"], 11)
        self.register("momentum_10", lambda df: df["close"] - df["close"].shift(10), FeatureCategory.MOMENTUM,
                     "Momentum(10)", ["close"], 11)
        self.register("adx_14", self._adx(14), FeatureCategory.MOMENTUM,
                     "ADX(14) trend strength", ["high", "low", "close"], 15)
        self.register("cci_20", lambda df: ((df["high"] + df["low"] + df["close"]) / 3 - ((df["high"] + df["low"] + df["close"]) / 3).rolling(20).mean()) / (0.015 * ((df["high"] + df["low"] + df["close"]) / 3).rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True).replace(0, np.nan)),
                     FeatureCategory.MOMENTUM, "CCI(20) using typical price", ["high", "low", "close"], 21)
        self.register("willr_14", lambda df: -100 * (df["high"].rolling(14).max() - df["close"]) / (df["high"].rolling(14).max() - df["low"].rolling(14).min()).replace(0, np.nan),
                     FeatureCategory.MOMENTUM, "Williams %R(14)", ["high", "low", "close"], 15)
        self.register("stoch_rsi", self._stoch_rsi(14), FeatureCategory.MOMENTUM,
                     "Stochastic RSI(14)", ["close"], 17)
        self.register("aroon_up", self._aroon(25)[0], FeatureCategory.MOMENTUM,
                     "Aroon Up(25)", ["high"], 26)
        self.register("aroon_down", self._aroon(25)[1], FeatureCategory.MOMENTUM,
                     "Aroon Down(25)", ["low"], 26)

        # ── Extended volatility features ────────────────────────────────────
        self.register("keltner_upper", lambda df: df["close"].ewm(span=20, adjust=False).mean() + 2 * self._atr(20)(df),
                     FeatureCategory.VOLATILITY, "Keltner upper band", ["high", "low", "close"], 21)
        self.register("keltner_lower", lambda df: df["close"].ewm(span=20, adjust=False).mean() - 2 * self._atr(20)(df),
                     FeatureCategory.VOLATILITY, "Keltner lower band", ["high", "low", "close"], 21)
        self.register("hurst_exponent", self._hurst(64), FeatureCategory.VOLATILITY,
                     "Hurst exponent(64) trend persistence", ["close"], 65)
        self.register("rolling_skew_20", lambda df: df["close"].rolling(20).skew(), FeatureCategory.VOLATILITY,
                     "Rolling skew(20)", ["close"], 21)
        self.register("rolling_kurt_20", lambda df: df["close"].rolling(20).kurt(), FeatureCategory.VOLATILITY,
                     "Rolling kurtosis(20)", ["close"], 21)
        self.register("zscore20", lambda df: (df["close"] - df["close"].rolling(20).mean()) / df["close"].rolling(20).std().replace(0, np.nan),
                     FeatureCategory.VOLATILITY, "Price z-score(20)", ["close"], 21)

        # ── Extended volume features ────────────────────────────────────────
        self.register("obv", lambda df: (np.sign(df["close"].diff()).fillna(0) * df["volume"]).cumsum() if "volume" in df.columns else 0,
                     FeatureCategory.VOLUME, "On-balance volume", ["close", "volume"], 2)
        self.register("obv_slope", lambda df: (np.sign(df["close"].diff()).fillna(0) * df["volume"]).cumsum().diff(14) if "volume" in df.columns else 0,
                     FeatureCategory.VOLUME, "OBV slope(14)", ["close", "volume"], 15)
        self.register("mfi_14", self._mfi(14), FeatureCategory.VOLUME,
                     "Money Flow Index(14)", ["high", "low", "close", "volume"], 15)
        self.register("cmf_20", self._cmf(20), FeatureCategory.VOLUME,
                     "Chaikin Money Flow(20)", ["high", "low", "close", "volume"], 21)
        self.register("volume_zscore_20", lambda df: (df["volume"] - df["volume"].rolling(20).mean()) / df["volume"].rolling(20).std().replace(0, np.nan) if "volume" in df.columns else 0,
                     FeatureCategory.VOLUME, "Volume z-score(20)", ["volume"], 21)
        self.register("dollar_volume", lambda df: df["close"] * df["volume"] if "volume" in df.columns else df["close"],
                     FeatureCategory.VOLUME, "Dollar volume", ["close", "volume"], 1)

        # ── Extended microstructure features ────────────────────────────────
        self.register("close_position", lambda df: (df["close"] - df["low"].rolling(20).min()) / (df["high"].rolling(20).max() - df["low"].rolling(20).min()).replace(0, np.nan),
                     FeatureCategory.MICROSTRUCTURE, "Close position within 20-bar range (CSS %B)", ["high", "low", "close"], 21)
        self.register("intrabar_range", lambda df: (df["high"] - df["low"]) / df["close"], FeatureCategory.MICROSTRUCTURE,
                     "Intrabar range / close", ["high", "low", "close"], 1)
        self.register("gap", lambda df: df["open"] / df["close"].shift(1) - 1, FeatureCategory.MICROSTRUCTURE,
                     "Open-to-prev-close gap", ["open", "close"], 2)
        self.register("autocorr_5", lambda df: df["close"].pct_change().rolling(10).apply(lambda x: x.autocorr() if len(x) > 5 and x.var() > 0 else 0, raw=False),
                     FeatureCategory.MICROSTRUCTURE, "Return autocorrelation(10)", ["close"], 11)

        # ── Cross-asset placeholder fixes ───────────────────────────────────
        self.register("btc_dominance", lambda df: 0.0, FeatureCategory.CROSS_ASSET,
                     "BTC dominance placeholder (filled by microfeatures engine)", [], 1)
        self.register("eth_btc_ratio", lambda df: 0.0, FeatureCategory.CROSS_ASSET,
                     "ETH/BTC ratio placeholder (filled by microfeatures engine)", [], 1)
        self.register("sector_momentum", lambda df: 0.0, FeatureCategory.CROSS_ASSET,
                     "Sector momentum placeholder (filled by microfeatures engine)", [], 1)

        # ── Derivative / live features (filled by microfeatures engine) ─────
        self.register("funding_rate", lambda df: 0.0, FeatureCategory.DERIVATIVES,
                     "Funding rate placeholder (filled by microfeatures engine)", [], 1)
        self.register("open_interest", lambda df: 0.0, FeatureCategory.DERIVATIVES,
                     "Open interest placeholder (filled by microfeatures engine)", [], 1)
        self.register("mark_basis", lambda df: 0.0, FeatureCategory.DERIVATIVES,
                     "Mark-to-spot basis placeholder (filled by microfeatures engine)", [], 1)

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

    def compute(self, df: pd.DataFrame, features: List[str], apply_normalization: bool = True) -> pd.DataFrame:
        """Compute requested features for a DataFrame.

        When `apply_normalization` is True (default), each computed feature is
        normalized according to its registered `NormalizationType`. This closes
        the gap where normalization was stored in metadata but never applied.
        """
        result = df.copy()
        for name in features:
            if name in self._feature_fns:
                try:
                    col = self._feature_fns[name](df)
                    if apply_normalization:
                        meta = self.registry.get(name)
                        if meta is not None and meta.normalization != NormalizationType.NONE:
                            col = _normalize_series(col, meta.normalization, meta.normalization_params)
                    result[name] = col
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

    def _macd_hist(self) -> Callable[[pd.DataFrame], pd.Series]:
        def _calc(df: pd.DataFrame) -> pd.Series:
            ema12 = df["close"].ewm(span=12, adjust=False).mean()
            ema26 = df["close"].ewm(span=26, adjust=False).mean()
            macd = ema12 - ema26
            signal = macd.ewm(span=9, adjust=False).mean()
            return macd - signal
        return _calc

    def _adx(self, period: int) -> Callable[[pd.DataFrame], pd.Series]:
        def _calc(df: pd.DataFrame) -> pd.Series:
            up = df["high"].diff()
            down = -df["low"].diff()
            plus_dm = np.where((up > down) & (up > 0), up, 0.0)
            minus_dm = np.where((down > up) & (down > 0), down, 0.0)
            tr = pd.concat([
                df["high"] - df["low"],
                (df["high"] - df["close"].shift()).abs(),
                (df["low"] - df["close"].shift()).abs(),
            ], axis=1).max(axis=1)
            atr = tr.rolling(period).mean().replace(0, np.nan)
            plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(period).mean() / atr
            minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(period).mean() / atr
            dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
            return dx.rolling(period).mean()
        return _calc

    def _stoch_rsi(self, period: int) -> Callable[[pd.DataFrame], pd.Series]:
        def _calc(df: pd.DataFrame) -> pd.Series:
            delta = df["close"].diff()
            gain = delta.clip(lower=0).rolling(period).mean()
            loss = (-delta.clip(upper=0)).rolling(period).mean()
            rs = gain / loss.replace(0, np.nan)
            rsi = 100 - (100 / (1 + rs))
            lo = rsi.rolling(period).min()
            hi = rsi.rolling(period).max()
            return (rsi - lo) / (hi - lo).replace(0, np.nan)
        return _calc

    def _hurst(self, max_lag: int) -> Callable[[pd.DataFrame], pd.Series]:
        import warnings
        def _calc(df: pd.DataFrame) -> pd.Series:
            closes = df["close"].to_numpy()
            out = np.full(len(closes), np.nan)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                for i in range(max_lag * 3, len(closes)):
                    window = closes[i - max_lag * 3 : i]
                    if len(window) < max_lag * 3:
                        continue
                    lags = range(2, max_lag)
                    ts = np.log(window)
                    tau = [np.std(np.subtract(ts[lag:], ts[:-lag])) for lag in lags]
                    tau = np.array(tau)
                    mask = tau > 0
                    if mask.sum() < 2:
                        continue
                    poly = np.polyfit(np.log(list(lags))[mask.tolist()], np.log(tau[mask]), 1)
                    out[i] = poly[0]
            return pd.Series(out, index=df.index)
        return _calc

    def _mfi(self, period: int) -> Callable[[pd.DataFrame], pd.Series]:
        def _calc(df: pd.DataFrame) -> pd.Series:
            if "volume" not in df.columns:
                return pd.Series(np.nan, index=df.index)
            tp = (df["high"] + df["low"] + df["close"]) / 3
            mf = tp * df["volume"]
            pos = mf.where(tp > tp.shift(1), 0.0).rolling(period).sum()
            neg = mf.where(tp < tp.shift(1), 0.0).rolling(period).sum()
            return 100 - (100 / (1 + pos / neg.replace(0, np.nan)))
        return _calc

    def _aroon(self, period: int) -> tuple:
        """Correct Aroon Up/Down: 100*(period - days_since_rolling_high/low)/period."""
        def _make(is_high: bool):
            def _calc(df: pd.DataFrame) -> pd.Series:
                col = df["high"] if is_high else df["low"]
                def _days_since(x):
                    if is_high:
                        idx = np.where(x == x.max())[0]
                    else:
                        idx = np.where(x == x.min())[0]
                    days = (len(x) - 1) - idx[-1]
                    return 100.0 * (period - days) / period
                return col.rolling(period).apply(_days_since, raw=True)
            return _calc
        return _make(True), _make(False)

    def _cmf(self, period: int) -> Callable[[pd.DataFrame], pd.Series]:
        def _calc(df: pd.DataFrame) -> pd.Series:
            if "volume" not in df.columns:
                return pd.Series(np.nan, index=df.index)
            hl = (df["high"] - df["low"]).replace(0, np.nan)
            mfm = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / hl
            mfv = mfm.fillna(0) * df["volume"]
            vol_sum = df["volume"].rolling(period).sum().replace(0, np.nan)
            return mfv.rolling(period).sum() / vol_sum
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