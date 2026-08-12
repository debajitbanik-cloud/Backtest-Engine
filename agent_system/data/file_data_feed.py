"""
File-based data feed that reads aggregated OHLCV candle files
from the shared data directory.
"""
from __future__ import annotations
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

from core.event_bus import EventBus, Event, EventType, event_bus
from data.free_crypto_feed import CandleData


class FileDataFeedAgent:
    """
    Reads OHLCV candles from JSON files and replays them as events.
    Used for backtesting with historical data.
    """
    
    def __init__(self, data_dir: str, event_bus: EventBus = None, 
                 symbols: List[str] = None, timeframes: List[str] = None,
                 replay_speed: float = 1.0):
        self.data_dir = Path(data_dir)
        self.event_bus = event_bus or event_bus
        self.symbols = symbols or ["SOLUSDT", "XAUTUSDT"]
        self.timeframes = timeframes or ["1m", "5m", "15m", "1h"]
        self.replay_speed = replay_speed  # 1.0 = real-time, 0.0 = fastest
        self._running = False
        self._replay_task: asyncio.Task = None
    
    async def start(self) -> None:
        """Start replaying historical data."""
        self._running = True
        self._replay_task = asyncio.create_task(self._replay_loop())
        print(f"File data feed started: {self.symbols} {self.timeframes}")
    
    async def stop(self) -> None:
        """Stop the feed."""
        self._running = False
        if self._replay_task:
            self._replay_task.cancel()
    
    async def _replay_loop(self) -> None:
        """Replay candle data in chronological order."""
        # Load all candles for all symbols/timeframes
        all_candles = []
        
        for symbol in self.symbols:
            for tf in self.timeframes:
                candles = await self._load_candles(symbol, tf)
                all_candles.extend(candles)
        
        # Sort by timestamp
        all_candles.sort(key=lambda c: c.timestamp)
        print(f"Loaded {len(all_candles)} total candles for replay")
        
        # Limit to manageable number for backtesting
        max_candles = 5000
        if len(all_candles) > max_candles:
            all_candles = all_candles[-max_candles:]  # Take last N candles
            print(f"Limited to {len(all_candles)} candles (last {max_candles})")
        
        if not all_candles:
            return
        
        # Replay with timing
        prev_ts = None
        for candle in all_candles:
            if not self._running:
                break
            
            # Wait based on time delta between candles
            if prev_ts is not None and self.replay_speed > 0:
                delta_ms = (candle.timestamp - prev_ts).total_seconds() * 1000
                if delta_ms > 0 and delta_ms < 3600000:  # Cap at 1 hour
                    await asyncio.sleep(delta_ms / self.replay_speed / 1000)
            
            prev_ts = candle.timestamp
            
            # Publish candle event
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
                source_agent="FileDataFeed"
            ))
            
            # Publish tick event
            await self.event_bus.publish(Event(
                type=EventType.MARKET_TICK,
                payload={
                    "symbol": candle.symbol,
                    "price": candle.close,
                    "volume": candle.volume,
                    "timestamp": candle.timestamp
                },
                source_agent="FileDataFeed"
            ))
        
        print("Data replay complete")
    
    async def _load_candles(self, symbol: str, timeframe: str) -> List[CandleData]:
        """Load candles from JSON file."""
        filepath = self.data_dir / f"{symbol}_{timeframe}.json"
        
        if not filepath.exists():
            print(f"  Warning: {filepath} not found")
            return []
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        candles = []
        for d in data:
            candle = CandleData(
                symbol=d['symbol'],
                timeframe=d['timeframe'],
                open=float(d['open']),
                high=float(d['high']),
                low=float(d['low']),
                close=float(d['close']),
                volume=float(d['volume']),
                timestamp=self._parse_ts(d['timestamp']),
                closed=d.get('closed', True)
            )
            candles.append(candle)
        
        print(f"  Loaded {len(candles)} {timeframe} candles for {symbol}")
        return candles
    
    def _parse_ts(self, ts: Any) -> datetime:
        """Parse timestamp that might be ISO string or number."""
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts / 1000 if ts > 1e10 else ts)
        elif isinstance(ts, str):
            return datetime.fromisoformat(ts.replace('Z', ''))
        return datetime.utcnow()