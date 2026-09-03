"""
Realtime Asset Class Price Banner
==================================
Fetches realtime prices across asset classes (crypto, equity indices,
commodities, forex) via Yahoo Finance fast_info, fetched concurrently and
cached briefly so the UI banner can poll without hammering the API.

Slim banner mode: BTC (from Delta), Gold, Oil, DXY with left-to-right marquee.
Full banner mode: asset classes via yfinance.
"""
from __future__ import annotations

import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Full curated asset classes for the Strategy Library / Analytics
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

# Slim banner tickers: BTC, Gold, Oil, DXY (left-to-right marquee)
SLIM_BANNER_TICKERS: List[Dict[str, str]] = [
    {"ticker": "BTC-USD", "symbol": "BTC", "label": "Bitcoin", "emoji": "₿", "class": "crypto", "class_label": "Crypto"},
    {"ticker": "GC=F", "symbol": "GOLD", "label": "Gold", "emoji": "🥇", "class": "commodities", "class_label": "Commodities"},
    {"ticker": "CL=F", "symbol": "OIL", "label": "WTI Crude", "emoji": "🛢️", "class": "commodities", "class_label": "Commodities"},
    {"ticker": "DX-Y.NYB", "symbol": "DXY", "label": "Dollar Index", "emoji": "💵", "class": "forex", "class_label": "Forex"},
]

# Flattened curated list of (ticker, asset_class, label)
CURATED: List[Dict[str, str]] = [
    {"ticker": t, "class": ac["class"], "class_label": ac["label"]}
    for ac in ASSET_CLASSES
    for t in ac["tickers"]
]

_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0}
_SLIM_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0}
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
            "symbol": item.get("symbol") or ticker.replace("-USD", "").replace("=X", "").replace("^", ""),
            "label": item.get("label") or ticker,
            "emoji": item.get("emoji") or "",
            "class": item.get("class", "unknown"),
            "class_label": item.get("class_label", "Unknown"),
            "last": round(last, 4),
            "previous_close": round(prev, 4),
            "change": round(last - prev, 4),
            "change_pct": round((last / prev - 1) * 100, 2),
        }
    except Exception:
        return None


def fetch_banner(force: bool = False, slim: bool = False, btc_price: float = 0.0) -> Dict[str, Any]:
    """Fetch all curated tickers concurrently with a short TTL cache.

    Args:
        force: Bypass cache
        slim: If True, return only the 4-asset slim banner (BTC, Gold, Oil, DXY)
        btc_price: Optional BTC price to use for slim banner (from Delta)
    """
    now = time.time()
    cache = _SLIM_CACHE if slim else _CACHE
    if not force and cache["data"] is not None and (now - cache["ts"]) < CACHE_TTL:
        return cache["data"]

    items = SLIM_BANNER_TICKERS if slim else CURATED
    records: List[Optional[Dict[str, Any]]] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(_fetch_one, item) for item in items]
        for fut in as_completed(futures):
            try:
                result = fut.result(timeout=3.0)
                if result:
                    # Override BTC price with Delta price if provided
                    if slim and result["symbol"] == "BTC" and btc_price > 0:
                        result["last"] = round(btc_price, 2)
                        result["change"] = round(btc_price - result["previous_close"], 4)
                        result["change_pct"] = round((btc_price / result["previous_close"] - 1) * 100, 2)
                    records.append(result)
                else:
                    records.append(None)
            except Exception:
                records.append(None)

    records = [r for r in records if r is not None]

    if slim:
        result = {
            "banner": records,
            "count": len(records),
            "updated": datetime.now(timezone.utc).isoformat(),
        }
    else:
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

    cache["data"] = result
    cache["ts"] = now
    return result


def clear_cache() -> None:
    _CACHE["data"] = None
    _CACHE["ts"] = 0.0
    _SLIM_CACHE["data"] = None
    _SLIM_CACHE["ts"] = 0.0


if __name__ == "__main__":
    import json

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        data = fetch_banner(force=True)
        print(json.dumps(data, indent=2))
        print("\n--- SLIM BANNER ---")
        slim = fetch_banner(force=True, slim=True)
        print(json.dumps(slim, indent=2))