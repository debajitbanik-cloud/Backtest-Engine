"""
Delta Exchange Data Feed
WebSocket and REST integration for Delta Exchange market data.
"""
from __future__ import annotations
import asyncio
import json
import hmac
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable, Set
from enum import Enum
from urllib.parse import urlencode

import aiohttp
import websockets


class DeltaEnvironment(Enum):
    """Delta Exchange environments."""
    PRODUCTION = "production"
    TESTNET = "testnet"


@dataclass
class DeltaConfig:
    """Delta Exchange configuration."""
    api_key: str = ""
    api_secret: str = ""
    environment: DeltaEnvironment = DeltaEnvironment.PRODUCTION
    ws_url: str = "wss://socket.delta.exchange"
    rest_url: str = "https://api.delta.exchange"
    testnet_ws_url: str = "wss://socket.testnet.delta.exchange"
    testnet_rest_url: str = "https://api.testnet.delta.exchange"
    reconnect_interval: int = 5
    max_reconnect_attempts: int = 10
    ping_interval: int = 20


@dataclass
class MarketData:
    """Standardized market data."""
    symbol: str
    price: float
    volume: float
    timestamp: datetime
    bid: Optional[float] = None
    ask: Optional[float] = None
    bid_size: Optional[float] = None
    ask_size: Optional[float] = None
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None
    change_24h: Optional[float] = None


@dataclass
class CandleData:
    """Candle/OHLCV data."""
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: datetime
    closed: bool = True


class DeltaExchangeFeed:
    """
    Delta Exchange data feed with WebSocket and REST support.
    
    Features:
    - Real-time ticker via WebSocket
    - Candle data subscription
    - Orderbook depth
    - REST API for historical data
    - Authentication for private endpoints
    - Automatic reconnection
    """
    
    def __init__(self, config: DeltaConfig):
        self.config = config
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._subscriptions: Set[str] = set()
        self._callbacks: Dict[str, List[Callable]] = {
            "ticker": [],
            "candle": [],
            "orderbook": [],
            "trade": [],
        }
        self._reconnect_task: Optional[asyncio.Task] = None
        self._last_ping = 0
    
    @property
    def ws_url(self) -> str:
        if self.config.environment == DeltaEnvironment.TESTNET:
            return self.config.testnet_ws_url
        return self.config.ws_url
    
    @property
    def rest_url(self) -> str:
        if self.config.environment == DeltaEnvironment.TESTNET:
            return self.config.testnet_rest_url
        return self.config.rest_url
    
    async def connect(self) -> None:
        """Establish WebSocket connection."""
        self._session = aiohttp.ClientSession()
        await self._connect_ws()
        self._running = True
        asyncio.create_task(self._ping_loop())
    
    async def _connect_ws(self) -> None:
        """Connect to WebSocket with authentication."""
        try:
            self._ws = await websockets.connect(self.ws_url)
            
            # Authenticate if credentials provided
            if self.config.api_key and self.config.api_secret:
                await self._authenticate()
            
            # Resubscribe to previous channels
            for channel in self._subscriptions:
                await self._send({"type": "subscribe", "channel": channel})
            
            # Start message handler
            asyncio.create_task(self._message_handler())
            
        except Exception as e:
            print(f"Delta WS connection failed: {e}")
            await self._schedule_reconnect()
    
    async def _authenticate(self) -> None:
        """Authenticate WebSocket connection."""
        timestamp = str(int(time.time()))
        method = "GET"
        path = "/v2/ws/auth"
        payload = ""
        
        signature = self._generate_signature(timestamp, method, path, payload)
        
        auth_msg = {
            "type": "auth",
            "api_key": self.config.api_key,
            "timestamp": timestamp,
            "signature": signature
        }
        
        await self._send(auth_msg)
    
    def _generate_signature(self, timestamp: str, method: str, path: str, payload: str) -> str:
        """Generate HMAC signature for authentication."""
        message = timestamp + method + path + payload
        return hmac.new(
            self.config.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
    
    async def _send(self, message: Dict) -> None:
        """Send message over WebSocket."""
        if self._ws and not self._ws.closed:
            await self._ws.send(json.dumps(message))
    
    async def _message_handler(self) -> None:
        """Handle incoming WebSocket messages."""
        try:
            async for message in self._ws:
                data = json.loads(message)
                await self._process_message(data)
        except websockets.exceptions.ConnectionClosed:
            print("Delta WS connection closed")
            if self._running:
                await self._schedule_reconnect()
        except Exception as e:
            print(f"Delta WS message handler error: {e}")
    
    async def _process_message(self, data: Dict) -> None:
        """Process incoming message by type."""
        msg_type = data.get("type")
        channel = data.get("channel")
        
        if msg_type == "ticker" or channel == "ticker":
            await self._handle_ticker(data)
        elif msg_type == "candle" or channel == "candle":
            await self._handle_candle(data)
        elif msg_type == "orderbook" or channel == "orderbook":
            await self._handle_orderbook(data)
        elif msg_type == "trade" or channel == "trade":
            await self._handle_trade(data)
        elif msg_type == "pong":
            self._last_ping = time.time()
    
    async def _handle_ticker(self, data: Dict) -> None:
        """Process ticker update."""
        result = data.get("result", data)
        for item in (result if isinstance(result, list) else [result]):
            market_data = MarketData(
                symbol=item.get("symbol", ""),
                price=float(item.get("close", item.get("mark_price", 0))),
                volume=float(item.get("volume", 0)),
                timestamp=datetime.utcnow(),
                bid=float(item.get("bid", 0)) if item.get("bid") else None,
                ask=float(item.get("ask", 0)) if item.get("ask") else None,
                high_24h=float(item.get("high", 0)) if item.get("high") else None,
                low_24h=float(item.get("low", 0)) if item.get("low") else None,
                change_24h=float(item.get("change_24h", 0)) if item.get("change_24h") else None
            )
            await self._emit("ticker", market_data)
    
    async def _handle_candle(self, data: Dict) -> None:
        """Process candle update."""
        result = data.get("result", data)
        for item in (result if isinstance(result, list) else [result]):
            candle = CandleData(
                symbol=item.get("symbol", ""),
                timeframe=item.get("resolution", "1m"),
                open=float(item.get("open", 0)),
                high=float(item.get("high", 0)),
                low=float(item.get("low", 0)),
                close=float(item.get("close", 0)),
                volume=float(item.get("volume", 0)),
                timestamp=datetime.fromtimestamp(item.get("time", time.time())),
                closed=item.get("closed", True)
            )
            await self._emit("candle", candle)
    
    async def _handle_orderbook(self, data: Dict) -> None:
        """Process orderbook update."""
        await self._emit("orderbook", data)
    
    async def _handle_trade(self, data: Dict) -> None:
        """Process trade update."""
        await self._emit("trade", data)
    
    async def _emit(self, event_type: str, data: Any) -> None:
        """Emit event to all registered callbacks."""
        for callback in self._callbacks.get(event_type, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                print(f"Callback error for {event_type}: {e}")
    
    def on_ticker(self, callback: Callable[[MarketData], Any]) -> None:
        """Register ticker callback."""
        self._callbacks["ticker"].append(callback)
    
    def on_candle(self, callback: Callable[[CandleData], Any]) -> None:
        """Register candle callback."""
        self._callbacks["candle"].append(callback)
    
    def on_orderbook(self, callback: Callable[[Dict], Any]) -> None:
        """Register orderbook callback."""
        self._callbacks["orderbook"].append(callback)
    
    def on_trade(self, callback: Callable[[Dict], Any]) -> None:
        """Register trade callback."""
        self._callbacks["trade"].append(callback)
    
    async def subscribe_ticker(self, symbols: List[str]) -> None:
        """Subscribe to ticker updates for symbols."""
        for symbol in symbols:
            channel = f"ticker.{symbol}"
            self._subscriptions.add(channel)
            if self._ws and not self._ws.closed:
                await self._send({"type": "subscribe", "channel": channel})
    
    async def subscribe_candles(self, symbols: List[str], timeframe: str = "1m") -> None:
        """Subscribe to candle updates."""
        for symbol in symbols:
            channel = f"candle.{timeframe}.{symbol}"
            self._subscriptions.add(channel)
            if self._ws and not self._ws.closed:
                await self._send({"type": "subscribe", "channel": channel})
    
    async def subscribe_orderbook(self, symbols: List[str], depth: int = 20) -> None:
        """Subscribe to orderbook updates."""
        for symbol in symbols:
            channel = f"orderbook.{depth}.{symbol}"
            self._subscriptions.add(channel)
            if self._ws and not self._ws.closed:
                await self._send({"type": "subscribe", "channel": channel})
    
    async def subscribe_trades(self, symbols: List[str]) -> None:
        """Subscribe to trade updates."""
        for symbol in symbols:
            channel = f"trade.{symbol}"
            self._subscriptions.add(channel)
            if self._ws and not self._ws.closed:
                await self._send({"type": "subscribe", "channel": channel})
    
    async def _ping_loop(self) -> None:
        """Send periodic pings to keep connection alive."""
        while self._running:
            await asyncio.sleep(self.config.ping_interval)
            if self._ws and not self._ws.closed:
                await self._send({"type": "ping"})
    
    async def _schedule_reconnect(self) -> None:
        """Schedule reconnection attempt."""
        if self._reconnect_task and not self._reconnect_task.done():
            return
        
        self._reconnect_task = asyncio.create_task(self._reconnect())
    
    async def _reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        for attempt in range(self.config.max_reconnect_attempts):
            if not self._running:
                return
            
            wait_time = self.config.reconnect_interval * (2 ** attempt)
            print(f"Delta WS reconnecting in {wait_time}s (attempt {attempt + 1})")
            await asyncio.sleep(wait_time)
            
            try:
                await self._connect_ws()
                print("Delta WS reconnected successfully")
                return
            except Exception as e:
                print(f"Reconnect attempt {attempt + 1} failed: {e}")
        
        print("Delta WS max reconnect attempts reached")
    
    # REST API methods
    async def get_historical_candles(self, symbol: str, resolution: str, 
                                    start: int, end: int) -> List[CandleData]:
        """Fetch historical candles via REST API."""
        if not self._session:
            self._session = aiohttp.ClientSession()
        
        params = {
            "symbol": symbol,
            "resolution": resolution,
            "start": start,
            "end": end
        }
        
        url = f"{self.rest_url}/v2/history/candles?{urlencode(params)}"
        
        async with self._session.get(url) as resp:
            data = await resp.json()
            result = data.get("result", [])
            
            return [
                CandleData(
                    symbol=symbol,
                    timeframe=resolution,
                    open=float(c["o"]),
                    high=float(c["h"]),
                    low=float(c["l"]),
                    close=float(c["c"]),
                    volume=float(c["v"]),
                    timestamp=datetime.fromtimestamp(c["t"]),
                    closed=True
                )
                for c in result
            ]
    
    async def get_ticker(self, symbol: str) -> MarketData:
        """Get current ticker via REST."""
        if not self._session:
            self._session = aiohttp.ClientSession()
        
        url = f"{self.rest_url}/v2/tickers/{symbol}"
        
        async with self._session.get(url) as resp:
            data = await resp.json()
            result = data.get("result", {})
            
            return MarketData(
                symbol=symbol,
                price=float(result.get("close", result.get("mark_price", 0))),
                volume=float(result.get("volume", 0)),
                timestamp=datetime.utcnow(),
                bid=float(result.get("bid", 0)) if result.get("bid") else None,
                ask=float(result.get("ask", 0)) if result.get("ask") else None,
                high_24h=float(result.get("high", 0)) if result.get("high") else None,
                low_24h=float(result.get("low", 0)) if result.get("low") else None,
                change_24h=float(result.get("change_24h", 0)) if result.get("change_24h") else None
            )
    
    async def get_products(self) -> List[Dict]:
        """Get all available products."""
        if not self._session:
            self._session = aiohttp.ClientSession()
        
        url = f"{self.rest_url}/v2/products"
        
        async with self._session.get(url) as resp:
            data = await resp.json()
            return data.get("result", [])
    
    async def close(self) -> None:
        """Close connections."""
        self._running = False
        
        if self._ws and not self._ws.closed:
            await self._ws.close()
        
        if self._session:
            await self._session.close()
        
        if self._reconnect_task:
            self._reconnect_task.cancel()


# Integration with agent system
class DeltaDataFeedAgent:
    """Agent wrapper for Delta Exchange feed."""
    
    def __init__(self, config: DeltaConfig, event_bus: EventBus = None):
        self.feed = DeltaExchangeFeed(config)
        self.event_bus = event_bus or event_bus
        self._symbols: List[str] = []
        self._timeframes: List[str] = ["1m", "5m", "15m", "1h"]
    
    async def start(self, symbols: List[str]) -> None:
        """Start feed for symbols."""
        self._symbols = symbols
        await self.feed.connect()
        
        # Register callbacks to publish to event bus
        self.feed.on_ticker(self._on_ticker)
        self.feed.on_candle(self._on_candle)
        
        # Subscribe to channels
        await self.feed.subscribe_ticker(symbols)
        for tf in self._timeframes:
            await self.feed.subscribe_candles(symbols, tf)
    
    async def _on_ticker(self, data: MarketData) -> None:
        """Publish ticker to event bus."""
        await self.event_bus.publish(Event(
            type=EventType.MARKET_TICK,
            payload={
                "symbol": data.symbol,
                "price": data.price,
                "volume": data.volume,
                "bid": data.bid,
                "ask": data.ask,
                "timestamp": data.timestamp
            },
            source_agent="DeltaDataFeed"
        ))
    
    async def _on_candle(self, data: CandleData) -> None:
        """Publish candle to event bus."""
        await self.event_bus.publish(Event(
            type=EventType.MARKET_CANDLE,
            payload={
                "symbol": data.symbol,
                "timeframe": data.timeframe,
                "candle": {
                    "open": data.open,
                    "high": data.high,
                    "low": data.low,
                    "close": data.close,
                    "volume": data.volume,
                    "timestamp": data.timestamp
                }
            },
            source_agent="DeltaDataFeed"
        ))
    
    async def stop(self) -> None:
        """Stop the feed."""
        await self.feed.close()