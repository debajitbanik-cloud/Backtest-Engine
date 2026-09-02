"""Economic calendar ingestion from Forex Factory's public JSON feed.

Fetches the current-week economic calendar from the official Firebase-hosted
feed (https://nfs.faireconomy.media/ff_calendar_thisweek.json), filters for
high-impact events, maps each event to the crypto/gold asset classes it is
most likely to move, and caches the result for up to 24 hours.

Unofficial but stable public feed (no auth required). Cached with a TTL so
the upstream is only queried at most once every 24h.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import socket
import time
from typing import Any, Dict, List, Optional

import aiohttp

log = logging.getLogger(__name__)

FF_THISWEEK_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FF_NEXTWEEK_URL = "https://nfs.faireconomy.media/ff_calendar_nextweek.json"

CACHE_TTL_SECONDS = 24 * 60 * 60  # refresh upstream at most once per 24h
CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "calendar_cache.json")
CACHE_FILE = os.path.abspath(CACHE_FILE)

# How far out to surface events (in hours). Beyond this they are omitted.
LOOKAHEAD_HOURS = 72

# Map each currency/country code to the asset classes it primarily drives.
# Crypto and gold are USD/risk-sentiment driven, so almost any major release
# can move them; we just weight the most influential ones.
CURRENCY_ASSETS: Dict[str, List[str]] = {
    "USD": ["BTC", "ETH", "SOL", "XRP", "XAU", "DOGE"],
    "EUR": ["BTC", "ETH", "SOL", "XAU"],
    "GBP": ["BTC", "ETH", "SOL", "XAU"],
    "JPY": ["BTC", "ETH", "XAU"],
    "CAD": ["BTC", "ETH", "SOL", "XAU"],
    "AUD": ["BTC", "ETH", "SOL", "XAU"],
    "NZD": ["BTC", "ETH", "XAU"],
    "CHF": ["BTC", "ETH", "XAU"],
    "CNY": ["BTC", "ETH", "SOL"],
    "USD/CAD": ["BTC", "ETH", "XAU"],
    "MYR": ["BTC", "ETH", "SOL"],
    "HKD": ["BTC", "ETH", "XAU"],
    "SGD": ["BTC", "ETH", "XAU"],
    "MXN": ["BTC", "ETH", "SOL", "XAU"],
    "BRL": ["BTC", "ETH", "SOL", "XAU"],
    "TRY": ["BTC", "ETH", "XAU"],
    "KRW": ["BTC", "ETH", "SOL"],
    "AUD/JPY": ["BTC", "ETH", "XAU"],
    "NZD/JPY": ["BTC", "ETH", "XAU"],
    "RUB": ["BTC", "XAU"],
    "INR": ["BTC", "ETH", "SOL"],
    "EUR/GBP": ["BTC", "ETH", "XAU"],
    "NGN": ["BTC", "ETH"],
    "ARS": ["BTC", "ETH", "XAU"],
    "THB": ["BTC", "ETH"],
    "IDR": ["BTC", "ETH"],
    "ZAR": ["BTC", "XAU"],
    "SAR": ["BTC", "ETH", "XAU"],
}

# Event titles that carry outsized market influence regardless of currency.
HIGH_VALUE_KEYWORDS = [
    "non-farm", "cpi", "inflation", "fomc", "fed", "federal", "interest rate",
    "cash rate", "overnight rate", "rate statement", "gdp", "employment change",
    "unemployment", "payroll", "pce", "retail sales", "ism", "pmt", "average hourly",
]

# Default mapping for currencies not explicitly listed above.
DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "XAU"]


class EconomicCalendar:
    """Fetches, caches and serves high-impact economic events."""

    def __init__(self, ttl_seconds: int = CACHE_TTL_SECONDS, cache_file: str = CACHE_FILE):
        self._ttl = ttl_seconds
        self._cache_file = cache_file
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: float = 0.0
        self._last_error: Optional[str] = None
        self._lock = asyncio.Lock()

    @staticmethod
    def _normalise_time(iso: str) -> Optional[int]:
        """Convert Forex Factory ISO date (+ timezone offset) to epoch seconds."""
        iso = (iso or "").strip()
        if not iso:
            return None
        try:
            # e.g. 2026-09-01T10:00:00-04:00
            if "+" in iso:
                iso = iso.replace("+", "+")
            dtm = dt.datetime.fromisoformat(iso)
            # Make naive UTC
            if dtm.tzinfo is not None:
                return int(dtm.timestamp())
            return int(dtm.astimezone(dt.timezone.utc).timestamp())
        except Exception:
            try:
                return int(time.mktime(dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S").timetuple()))
            except Exception:
                return None

    @staticmethod
    def map_assets(currency: str, title: str) -> List[str]:
        """Map a calendar event to the asset classes it can materially move."""
        cur = (currency or "").upper().strip()
        ttl = (title or "").lower()
        assets = list(CURRENCY_ASSETS.get(cur, DEFAULT_ASSETS))
        # Outsize events: broaden the blast radius.
        if any(k in ttl for k in HIGH_VALUE_KEYWORDS):
            assets = ["BTC", "ETH", "SOL", "XRP", "XAU", "DOGE"]
        # De-dupe, preserve order.
        seen, out = set(), []
        for a in assets:
            if a not in seen:
                seen.add(a)
                out.append(a)
        return out

    @staticmethod
    def explain_event(title: str, impact: str) -> str:
        """Short natural-language note for the UI/alert."""
        ttl = (title or "").lower()
        if "non-farm" in ttl:
            return "US jobs data; moves USD & risk assets. Strong print → USD up, crypto/gold pressured."
        if "cpi" in ttl or "inflation" in ttl:
            return "Inflation reading; drives Fed expectations. Higher CPI → USD up, gold down."
        if "fomc" in ttl or "fed" in ttl or "interest rate" in ttl or "cash rate" in ttl or "overnight rate" in ttl:
            return "Central bank rate decision; the biggest crypto/gold catalyst of the month."
        if "employment change" in ttl or "payroll" in ttl:
            return "Jobs report; strong labour market → hawkish USD, headwind for gold/crypto."
        if "gdp" in ttl:
            return "GDP growth reading; strong growth → risk-on for crypto, mixed for gold."
        if "retail sales" in ttl:
            return "Consumer spending; strong → USD up, gold pressured."
        if "ism" in ttl:
            return "Manufacturing/PMI gauge; signals economic health and risk appetite."
        return f"High-impact {impact.lower()} release; expected to raise volatility across linked assets."

    async def _fetch(self, url: str) -> List[Dict]:
        """Fetch raw JSON from the Forex Factory feed (IPv4)."""
        connector = aiohttp.TCPConnector(family=socket.AF_INET, ssl=False)
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                 "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
        async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                data = await resp.json(content_type=None)
        return data if isinstance(data, list) else []

    async def _load_from_upstream(self) -> List[Dict]:
        """Fetch the current week (fall back to next week if this week is empty)."""
        events = await self._fetch(FF_THISWEEK_URL)
        if not events:
            try:
                events = await self._fetch(FF_NEXTWEEK_URL)
            except Exception:
                pass
        return events

    async def get_events(self, include_medium: bool = False,
                         lookahead_hours: int = LOOKAHEAD_HOURS) -> Dict[str, Any]:
        """Return upcoming high-impact (default) or high+medium events.

        Cached for 24h; refreshes from Forex Factory when stale.
        """
        async with self._lock:
            now = time.time()
            if self._cache is not None and (now - self._cache_time) < self._ttl:
                events = self._cache
            else:
                try:
                    raw = await self._load_from_upstream()
                except Exception as e:
                    self._last_error = str(e)
                    log.warning("Economic calendar fetch failed: %s", e)
                    # Serve any previously cached data if we have a file on disk
                    cached = self._read_disk_cache()
                    if cached is not None:
                        events = cached
                    else:
                        events = []
                else:
                    events = self._process(raw)
                    self._cache = events
                    self._cache_time = now
                    self._write_disk_cache(events)

            return self._filter(events, include_medium=include_medium, lookahead_hours=lookahead_hours)

    def _process(self, raw: List[Dict]) -> List[Dict]:
        """Normalise all events into a consistent shape (cached wholesale)."""
        out = []
        now = time.time()
        for e in raw:
            try:
                impact = (e.get("impact") or "Low").strip()
                title = (e.get("title") or "").strip()
                currency = (e.get("country") or "USD").strip()
                ts = self._normalise_time(e.get("date") or "")
                if ts is None:
                    continue
                out.append({
                    "title": title,
                    "currency": currency,
                    "impact": impact,
                    "timestamp": ts,
                    "time_until_min": int((ts - now) // 60),
                    "forecast": e.get("forecast") or "",
                    "previous": e.get("previous") or "",
                    "assets": self.map_assets(currency, title),
                    "note": self.explain_event(title, impact),
                })
            except Exception:
                continue
        out.sort(key=lambda x: x["timestamp"])
        return out

    def _filter(self, events: List[Dict], include_medium: bool,
                lookahead_hours: int) -> Dict[str, Any]:
        now = time.time()
        horizon = now + lookahead_hours * 3600
        allowed = {"High"}
        if include_medium:
            allowed.add("Medium")
        upcoming = []
        recent = []
        for ev in events:
            if ev["impact"] not in allowed:
                continue
            if now - 3600 * 3 <= ev["timestamp"] <= horizon:
                upcoming.append(ev)
            elif ev["timestamp"] < now:
                recent.append(ev)
        upcoming.sort(key=lambda x: x["timestamp"])
        # First high-impact item nearest to now => recommended "next" alert.
        next_event = None
        for ev in upcoming:
            if ev["timestamp"] >= now:
                next_event = ev
                break
        return {
            "source": "Forex Factory",
            "fetched_at": int(time.time()),
            "refreshes_every_hours": CACHE_TTL_SECONDS // 3600,
            "next_event": next_event,
            "upcoming": upcoming,
            "recent": recent[:20],
            "high_impact_count": sum(1 for u in upcoming if u["impact"] == "High"),
        }

    def _read_disk_cache(self) -> Optional[List[Dict]]:
        try:
            if os.path.exists(self._cache_file):
                with open(self._cache_file, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def _write_disk_cache(self, events: List[Dict]) -> None:
        try:
            os.makedirs(os.path.dirname(self._cache_file), exist_ok=True)
            with open(self._cache_file, "w") as f:
                json.dump(events, f)
        except Exception:
            pass


economic_calendar = EconomicCalendar()
