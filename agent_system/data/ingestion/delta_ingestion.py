"""
Delta Exchange Ingestion Service — REST + WebSocket ingestion with canonical normalization.
"""
from __future__ import annotations

import asyncio
import json
import hmac
import hashlib
import time
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Callable

import socket
import aiohttp
import websockets

from shared.domain import Instrument, MarketData, Venue
from data.ingestion.normalizer import get_normalizer, CanonicalNormalizer
from data.ingestion.backbone import (
    get_event_backbone,
    EventBackbone,
    STREAM_MARKET_TICKS,
    STREAM_MARKET_CANDLES,
    STREAM_ORDERS,
    STREAM_FILLS,
    STREAM_POSITIONS,
)


class DeltaIngestion:
    """
    Delta Exchange (India) ingestion service.
    Handles REST polling + WebSocket streaming with canonical normalization
    and publishing to the event backbone.
    """

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        base_url: str = "https://api.india.delta.exchange",
        ws_url: str = "wss://socket.delta.exchange",
        symbols: Optional[List[str]] = None,
        timeframes: Optional[List[str]] = None,
        event_backbone: Optional[EventBackbone] = None,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.ws_url = ws_url
        self.symbols = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        self.timeframes = timeframes or ["1m", "5m", "15m", "1h", "4h"]
        self.normalizer = get_normalizer()
        self.event_backbone = event_backbone

        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._subscribed_symbols: Set[str] = set()
        self._instrument_cache: Dict[str, Any] = {}

    async def initialize(self) -> None:
        """Initialize HTTP session and event backbone."""
        self._session = aiohttp.ClientSession()
        if self.event_backbone is None:
            self.event_backbone = await get_event_backbone()
        await self._load_instruments()

    async def start(self) -> None:
        """Start REST polling and WebSocket streaming."""
        self._running = True

        # Start WebSocket
        self._tasks.append(asyncio.create_task(self._ws_loop()))

        # Start REST polling for candles
        for symbol in self.symbols:
            for tf in self.timeframes:
                self._tasks.append(asyncio.create_task(self._poll_candles(symbol, tf)))

        # Start ticker polling as fallback
        self._tasks.append(asyncio.create_task(self._poll_tickers()))

    async def stop(self) -> None:
        """Stop all ingestion tasks."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()

    # ── REST API ──────────────────────────────────────────────────────────────

    def _generate_signature(self, method: str, endpoint: str, payload: str = "") -> tuple[str, str]:
        timestamp = str(int(time.time()))
        signature_data = f"{timestamp}{method}{endpoint}{payload}"
        signature = hmac.new(
            self.api_secret.encode(),
            signature_data.encode(),
            hashlib.sha256,
        ).hexdigest()
        return timestamp, signature

    async def _request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Dict] = None,
        params: Optional[Dict] = None,
        authenticated: bool = False,
    ) -> Dict:
        import json as json_module
        if self._session is None:
            raise RuntimeError("Session not initialized")

        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}

        if authenticated:
            body = json_module.dumps(payload or {})
            signature_payload = body
            if params:
                qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
                signature_payload = f"{qs}{body}" if body else qs
            timestamp, signature = self._generate_signature(method, endpoint, signature_payload)
            headers.update({
                "api-key": self.api_key,
                "signature": signature,
                "timestamp": timestamp,
            })

        async with self._session.request(
            method, url, json=payload, params=params, headers=headers
        ) as resp:
            try:
                data = await resp.json(content_type=None)
            except Exception:
                data = {}
            if data is None:
                data = {}
            if not data.get("success", True):
                raise Exception(f"Delta API error: {data.get('error', 'Unknown error')}")
            return data

    async def _load_instruments(self) -> None:
        """Load instrument metadata from Delta."""
        try:
            data = await self._request("GET", "/v2/products")
            for product in data.get("result", []):
                self._instrument_cache[product["symbol"]] = product
        except Exception as e:
            print(f"Instrument load skipped: {e}")

    # ── WebSocket ─────────────────────────────────────────────────────────────

    async def _ws_loop(self) -> None:
        """Main WebSocket loop with reconnection."""
        while self._running:
            try:
                await self._ws_connect()
            except Exception as e:
                print(f"WebSocket error: {e}, reconnecting in 5s...")
                await asyncio.sleep(5)

    async def _ws_connect(self) -> None:
        """Connect to Delta WebSocket and subscribe to channels."""
        channels = []
        for symbol in self.symbols:
            channels.append(f"ticker.{symbol}")
            channels.append(f"trade.{symbol}")
            for tf in self.timeframes:
                channels.append(f"candle.{tf}.{symbol}")

        async with websockets.connect(self.ws_url) as ws:
            self._ws = ws

            # Subscribe
            await ws.send(json.dumps({
                "type": "subscribe",
                "payload": {"channels": channels},
            }))

            async for message in ws:
                try:
                    data = json.loads(message)
                    await self._handle_ws_message(data)
                except Exception as e:
                    print(f"WS message error: {e}")

    async def _handle_ws_message(self, data: Dict) -> None:
        """Route WebSocket messages to handlers."""
        msg_type = data.get("type")

        if msg_type == "ticker":
            await self._handle_ticker(data.get("payload", {}))
        elif msg_type == "trade":
            await self._handle_trade(data.get("payload", {}))
        elif msg_type == "candle":
            await self._handle_candle(data.get("payload", {}))
        elif msg_type == "orderbook":
            await self._handle_orderbook(data.get("payload", {}))
        elif msg_type == "order":
            await self._handle_order_update(data.get("payload", {}))
        elif msg_type == "position":
            await self._handle_position_update(data.get("payload", {}))

    # ── Message Handlers ──────────────────────────────────────────────────────

    async def _handle_ticker(self, payload: Dict) -> None:
        """Handle ticker update."""
        symbol = payload.get("symbol")
        if not symbol:
            return

        tick = self.normalizer.normalize_tick(
            venue=Venue.DELTA,
            venue_symbol=symbol,
            payload=payload,
        )
        await self.event_backbone.publish_tick(tick)

    async def _handle_trade(self, payload: Dict) -> None:
        """Handle trade (fill) event."""
        # Convert trade to fill
        symbol = payload.get("symbol")
        if not symbol:
            return

        fill = Fill(
            id=payload.get("id", ""),
            order_id=payload.get("order_id", ""),
            strategy_id=payload.get("strategy_id", "unknown"),
            instrument=self.normalizer.normalize_instrument(Venue.DELTA, payload.get("symbol", "")),
            venue=Venue.DELTA,
            side=OrderSide.BUY if payload.get("side") == "buy" else OrderSide.SELL,
            quantity=Decimal(str(payload.get("size", 0))),
            price=Decimal(str(payload.get("price", 0))),
            commission=Decimal(str(payload.get("fee", 0))),
            timestamp=datetime.fromtimestamp(payload.get("timestamp", time.time())),
        )
        await self.event_backbone.publish_fill(fill)

    async def _handle_candle(self, payload: Dict) -> None:
        """Handle candle update."""
        symbol = payload.get("symbol")
        interval = payload.get("interval", "1m")
        if not symbol:
            return

        candle = self.normalizer.normalize_candle(
            venue=Venue.DELTA,
            venue_symbol=symbol,
            payload=payload,
            interval=payload.get("interval", "1m"),
        )
        await self.event_backbone.publish_candle(candle)

    async def _handle_orderbook(self, payload: Dict) -> None:
        """Handle orderbook update (convert to tick)."""
        # Orderbook updates can be used for microstructure features
        pass

    async def _handle_order_update(self, payload: Dict) -> None:
        """Handle order status update."""
        order = self.normalizer.normalize_order(
            venue=Venue.DELTA,
            venue_symbol=payload.get("symbol", ""),
            payload=payload,
            strategy_id=payload.get("strategy_id", "unknown"),
        )
        await self.event_backbone.publish_order(order)

    async def _handle_position_update(self, payload: Dict) -> None:
        """Handle position update."""
        position = self.normalizer.normalize_position(
            venue=Venue.DELTA,
            venue_symbol=payload.get("symbol", ""),
            payload=payload,
            strategy_id=payload.get("strategy_id", "unknown"),
        )
        await self.event_backbone.publish_position(position)

    # ── REST Polling Fallbacks ────────────────────────────────────────────────

    async def _poll_tickers(self, interval: float = 5.0) -> None:
        """Poll tickers via REST as WebSocket fallback."""
        while self._running:
            try:
                for symbol in self.symbols:
                    data = await self._request("GET", f"/v2/tickers/{symbol}")
                    result = data.get("result") or {}
                    if result.get("symbol"):
                        await self._handle_ticker(result)
            except Exception as e:
                print(f"Ticker poll error: {e}")
            await asyncio.sleep(interval)

    async def _poll_candles(self, symbol: str, timeframe: str, interval: float = 60.0) -> None:
        """Poll candles via REST."""
        while self._running:
            try:
                end = int(time.time())
                start = end - 150 * 60 * 5
                data = await self._request("GET", f"/v2/history/candles", params={
                    "symbol": symbol,
                    "resolution": timeframe,
                    "start": start,
                    "end": end,
                })
                candles = data.get("result") or []
                for candle in candles[-1:]:  # Only latest
                    await self._handle_candle({
                        **candle,
                        "symbol": symbol,
                        "interval": timeframe,
                    })
            except Exception as e:
                print(f"Candle poll error for {symbol} {timeframe}: {e}")
            await asyncio.sleep(interval)

    # ── Authenticated Endpoints ───────────────────────────────────────────────

    async def get_balances(self) -> Dict[str, Decimal]:
        data = await self._request("GET", "/v2/wallet/balances", authenticated=True)
        return {b["asset_symbol"]: Decimal(str(b["available_balance"])) for b in data.get("result", [])}

    async def get_positions(self) -> List:
        data = await self._request("GET", "/v2/positions", authenticated=True)
        return data.get("result", [])

    async def get_fills(self, since: Optional[datetime] = None) -> List:
        params = {}
        if since:
            params["start_time"] = int(since.timestamp())
        data = await self._request("GET", "/v2/fills", params=params, authenticated=True)
        return data.get("result", [])


import time
from datetime import datetime
from decimal import Decimal