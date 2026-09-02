"""
Realtime Asset Class Price Banner
==================================
Fetches realtime prices across asset classes (crypto, equity indices,
commodities, forex) via Yahoo Finance fast_info, fetched concurrently and
cached briefly so the UI banner can poll without hammering the API.
"""
from __future__ import annotations

import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

ASSET_CLASSES: List[Dict[str, Any]] = [
    {"class": "crypto", "label": "Crypto", "tickers": [
        "BTC-USD", "ETH-USD", "SOL-USD",
    ]},
    {"class": "equities", "label": "Indices", "tickers": [
        "^GSPC", "^IXIC", "^DJI",
    ]},
    {"class": "commodities", "label": "Commodities", "tickers": [
        "GC=F", "SI=F", "CL=F",
    ]},
    {"class": "forex", "label": "Forex", "tickers": [
        "EURUSD=X", "GBPUSD=X", "USDJPY=X",
    ]},
]

# Flattened curated list of (ticker, asset_class, label)
CURATED: List[Dict[str, str]] = [
    {"ticker": t, "class": ac["class"], "class_label": ac["label"]}
    for ac in ASSET_CLASSES
    for t in ac["tickers"]
]

_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0}
CACHE_TTL = 5.0  # seconds


def _fetch_one(item: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Fetch a single ticker's fast_info and return a normalized record."""
    import yfinance as yf

    ticker = item["ticker"]
    try:
        info = yf.Ticker(ticker).fast_info
        last = float(info.last_price)
        prev = float(info.previous_close)
        if not last or not prev:
            return None
        return {
            "ticker": ticker,
            "symbol": ticker.replace("-USD", "").replace("=X", "").replace("^", ""),
            "class": item["class"],
            "class_label": item["class_label"],
            "last": round(last, 4),
            "previous_close": round(prev, 4),
            "change": round(last - prev, 4),
            "change_pct": round((last / prev - 1) * 100, 2),
        }
    except Exception:
        return None


def fetch_banner(force: bool = False) -> Dict[str, Any]:
    """Fetch all curated tickers concurrently with a short TTL cache."""
    now = time.time()
    if not force and _CACHE["data"] is not None and (now - _CACHE["ts"]) < CACHE_TTL:
        return _CACHE["data"]

    records: List[Optional[Dict[str, Any]]] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(_fetch_one, item) for item in CURATED]
        for fut in as_completed(futures):
            try:
                records.append(fut.result())
            except Exception:
                records.append(None)

    records = [r for r in records if r is not None]

    # Group by asset class preserving curated order
    grouped = {}
    for ac in ASSET_CLASSES:
        grouped[ac["class"]] = {
            "label": ac["label"],
            "assets": [r for r in records if r["class"] == ac["class"]],
        }

    result = {
        "classes": grouped,
        "assets": records,
        "count": len(records),
        "updated": datetime.now(timezone.utc).isoformat(),
    }
    _CACHE["data"] = result
    _CACHE["ts"] = now
    return result


def clear_cache() -> None:
    _CACHE["data"] = None
    _CACHE["ts"] = 0.0


if __name__ == "__main__":
    import json

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        data = fetch_banner(force=True)
    print(json.dumps(data, indent=2))