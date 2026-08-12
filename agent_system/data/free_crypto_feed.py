"""
Free Crypto Data Feed using CCXT with Binance public API.
No API key required for market data.
"""
from __future__ import annotations
import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable

import ccxt

from core.event_bus import EventBus, Event, EventType, event_bus
from data.delta_exchange_feed import MarketData, CandleData


@dataclass
class FreeFeedConfig:
    """Configuration for free crypto data feed."""
    exchange: str = "binance"        # CCXT exchange id
    symbols: List[str] = field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
    timeframes: List[str] = field(default_factory=lambda: ["1m", "5m", "15m"])
    cache_dir: str = "data/cache"
    rate_limit: bool = True
    enable_websocket: bool = False   # CCXT WS requires more setup


class FreeCryptoFeed:
    """
    Free OHLCV data feed using CCXT and Binance public API.
    
    Features:
    - Fetch historical OHLCV from Binance (no API key)
    - Cache data locally to avoid repeated API calls
    - Poll for new candles
    - Publish events to agent system event bus
    """
    
    def __init__(self, config: FreeFeedConfig, event_bus: EventBus = None):
        self.config = config
        self.event_bus = event_bus or event_bus
        self.exchange = getattr(ccxt, config.exchange)({
            'enableRateLimit': config.rate_limit,
        })
        self.cache_dir = Path(config.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._running = False
        self._callbacks: Dict[str, List[Callable]] = {
            "ticker": [],
            "candle": [],
        }
        self._last_candles: Dict[str, Dict[str, CandleData]] = {}
    
    async def initialize(self) -> None:
        """Load exchange markets."""
        await asyncio.to_thread(self.exchange.load_markets)
        print(f"FreeCryptoFeed initialized: {self.config.exchange} with {len(self.exchange.markets)} markets")
    
    async def start(self) -> None:
        """Start polling for data."""
        self._running = True
        
        # Initial historical load
        for symbol in self.config.symbols:
            for timeframe in self.config.timeframes:
                await self.fetch_and_publish_historical(symbol, timeframe, limit=1000)
        
        # Start polling loop
        asyncio.create_task(self._polling_loop())
    
    async def stop(self) -> None:
        """Stop the feed."""
        self._running = False
    
    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 1000,
                         since: int = None) -> List[CandleData]:
        """Fetch OHLCV from exchange with caching."""
        # Check cache first
        cache_path = self._cache_path(symbol, timeframe)
        cached = self._load_cache(cache_path)
        
        if cached and len(cached) >= limit:
            return cached[-limit:]
        
        # Fetch from exchange
        try:
            ohlcv = await asyncio.to_thread(
                self.exchange.fetch_ohlcv,
                symbol,
                timeframe,
                since,
                limit
            )
            
            candles = [
                CandleData(
                    symbol=symbol.replace('/', ''),
                    timeframe=timeframe,
                    open=float(c[1]),
                    high=float(c[2]),
                    low=float(c[3]),
                    close=float(c[4]),
                    volume=float(c[5]),
                    timestamp=datetime.fromtimestamp(c[0] / 1000),
                    closed=True
                )
                for c in ohlcv
            ]
            
            # Merge with cache and save
            merged = self._merge_candles(cached, candles)
            self._save_cache(cache_path, merged)
            
            return candles
        except Exception as e:
            print(f"Error fetching {symbol} {timeframe}: {e}")
            return cached or []
    
    async def fetch_and_publish_historical(self, symbol: str, timeframe: str, limit: int = 1000) -> None:
        """Fetch historical data and publish as candles."""
        candles = await self.fetch_ohlcv(symbol, timeframe, limit)
        
        for candle in candles:
            await self._publish_candle(candle)
        
        print(f"Loaded {len(candles)} {timeframe} candles for {symbol}")
    
    async def fetch_latest(self, symbol: str, timeframe: str) -> Optional[CandleData]:
        """Fetch latest candle for a symbol/timeframe."""
        candles = await self.fetch_ohlcv(symbol, timeframe, limit=2)
        return candles[-1] if candles else None
    
    async def _polling_loop(self) -> None:
        """Poll for new candles."""
        while self._running:
            for symbol in self.config.symbols:
                for timeframe in self.config.timeframes:
                    try:
                        latest = await self.fetch_latest(symbol, timeframe)
                        if latest:
                            key = f"{symbol}_{timeframe}"
                            last = self._last_candles.get(key)
                            
                            if not last or latest.timestamp != last.timestamp:
                                self._last_candles[key] = latest
                                await self._publish_candle(latest)
                    except Exception as e:
                        print(f"Polling error {symbol} {timeframe}: {e}")
            
            # Sleep based on shortest timeframe
            sleep_seconds = self._get_polling_interval()
            await asyncio.sleep(sleep_seconds)
    
    async def _publish_candle(self, candle: CandleData) -> None:
        """Publish candle to event bus."""
        await self.event_bus.publish(Event(
            type=EventType.MARKET_CANDLE,
            payload={
                "symbol": candle.symbol,
                "timeframe": candle.timeframe,
                "candle": {
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                    "timestamp": candle.timestamp
                }
            },
            source_agent="FreeCryptoFeed"
        ))
        
        # Also publish tick
        await self.event_bus.publish(Event(
            type=EventType.MARKET_TICK,
            payload={
                "symbol": candle.symbol,
                "price": candle.close,
                "volume": candle.volume,
                "timestamp": candle.timestamp
            },
            source_agent="FreeCryptoFeed"
        ))
    
    def _cache_path(self, symbol: str, timeframe: str) -> Path:
        """Get cache file path."""
        normalized = symbol.replace('/', '_')
        return self.cache_dir / f"{normalized}_{timeframe}.json"
    
    def _load_cache(self, path: Path) -> List[CandleData]:
        """Load cached candles."""
        if not path.exists():
            return []
        
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            
            return [
                CandleData(
                    symbol=d["symbol"],
                    timeframe=d["timeframe"],
                    open=d["open"],
                    high=d["high"],
                    low=d["low"],
                    close=d["close"],
                    volume=d["volume"],
                    timestamp=datetime.fromisoformat(d["timestamp"]),
                    closed=d.get("closed", True)
                )
                for d in data
            ]
        except Exception as e:
            print(f"Cache load error: {e}")
            return []
    
    def _save_cache(self, path: Path, candles: List[CandleData]) -> None:
        """Save candles to cache."""
        data = []
        for c in candles:
            d = {
                "symbol": c.symbol,
                "timeframe": c.timeframe,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
                "timestamp": c.timestamp.isoformat(),
                "closed": c.closed
            }
            data.append(d)
        
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _merge_candles(self, cached: List[CandleData], new: List[CandleData]) -> List[CandleData]:
        """Merge cached and new candles, removing duplicates."""
        combined = {}
        for c in cached + new:
            key = c.timestamp.isoformat()
            combined[key] = c
        
        return sorted(combined.values(), key=lambda x: x.timestamp)
    
    def _get_polling_interval(self) -> int:
        """Get polling interval based on shortest timeframe."""
        intervals = {
            "1m": 30, "3m": 60, "5m": 60, "15m": 60,
            "30m": 120, "1h": 120, "2h": 300, "4h": 300,
            "6h": 600, "8h": 600, "12h": 900, "1d": 1800
        }
        
        shortest = min(self.config.timeframes, key=lambda tf: intervals.get(tf, 300))
        return intervals.get(shortest, 60)
    
    def on_candle(self, callback: Callable[[CandleData], Any]) -> None:
        """Register candle callback."""
        self._callbacks["candle"].append(callback)
    
    def on_ticker(self, callback: Callable[[MarketData], Any]) -> None:
        """Register ticker callback."""
        self._callbacks["ticker"].append(callback)


# Agent wrapper for free feed
class FreeCryptoFeedAgent:
    """Agent wrapper for free crypto feed."""
    
    def __init__(self, config: FreeFeedConfig, event_bus: EventBus = None):
        self.feed = FreeCryptoFeed(config, event_bus)
    
    async def start(self) -> None:
        """Start the feed."""
        await self.feed.initialize()
        await self.feed.start()
    
    async def stop(self) -> None:
        """Stop the feed."""
        await self.feed.stop()