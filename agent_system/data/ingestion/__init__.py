"""
Data Ingestion — Canonical market data normalization and event backbone.
"""
from __future__ import annotations

from data.ingestion.delta_ingestion import DeltaIngestion
from data.ingestion.backbone import EventBackbone, get_event_backbone, STREAM_MARKET_TICKS, STREAM_MARKET_CANDLES, STREAM_ORDERS, STREAM_FILLS, STREAM_POSITIONS
from data.ingestion.normalizer import CanonicalNormalizer, get_normalizer
from data.ingestion.mt5_ingestion import MT5Ingestion

__all__ = [
    "DeltaIngestion",
    "MT5Ingestion",
    "CanonicalNormalizer",
    "EventBackbone",
    "get_event_backbone",
]