"""
MT5 Ingestion Bridge — runs on Windows host, publishes to VPS Redis Streams.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    mt5 = None

import redis.asyncio as redis

from shared.domain import (
    Instrument,
    MarketData,
    Order,
    Fill,
    Position,
    Venue,
    OrderSide,
    OrderType,
    TimeInForce,
    OrderStatus,
    FillStatus,
    PositionSide,
)

from data.ingestion.normalizer import get_normalizer, CanonicalNormalizer
from data.ingestion.backbone import EventBackbone, STREAM_MARKET_TICKS, STREAM_MARKET_CANDLES, STREAM_ORDERS, STREAM_FILLS, STREAM_POSITIONS


class MT5Ingestion:
    """
    MT5 ingestion bridge running on Windows host.
    Connects to MT5 terminal and publishes canonical events to VPS Redis.
    """

    def __init__(
        self,
        login: int,
        password: str,
        server: str,
        path: Optional[str] = None,
        redis_url: str = "redis://vps-host:6379/0",
        symbols: Optional[List[str]] = None,
        timeframes: Optional[List[str]] = None,
    ):
        if not MT5_AVAILABLE:
            raise RuntimeError("MetaTrader5 package not available. Install on Windows: pip install MetaTrader5")

        self.login = login
        self.password = password
        self.server = server
        self.path = path
        self.redis_url = redis_url
        self.symbols = symbols or ["BTCUSD", "ETHUSD", "XAUUSD"]
        self.timeframes = timeframes or ["1m", "5m", "15m", "1h", "4h"]

        self.normalizer = get_normalizer()
        self._redis: Optional[redis.Redis] = None
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._symbol_info_cache: Dict[str, Any] = {}
        self._last_candle_time: Dict[str, datetime] = {}

    async def connect(self) -> bool:
        """Initialize MT5 connection and Redis."""
        # Connect to MT5
        loop = asyncio.get_event_loop()
        initialized = await loop.run_in_executor(
            None,
            lambda: mt5.initialize(
                login=self.login,
                password=self.password,
                server=self.server,
                path=self.path,
            )
        )
        if not initialized:
            raise ConnectionError(f"MT5 init failed: {mt5.last_error()}")

        # Connect to VPS Redis
        self._redis = redis.from_url(
            "redis://localhost:6379/0",  # Will be overridden by env on VPS
            encoding="utf-8",
            decode_responses=True,
        )
        # Test connection
        await self._redis.ping()

        # Ensure symbols are in Market Watch
        for symbol in self.symbols:
            await self._ensure_symbol(symbol)

        return True

    async def start(self) -> None:
        """Start ingestion loops."""
        self._running = True

        # Start tick streaming
        for symbol in self.symbols:
            self._tasks.append(asyncio.create_task(self._stream_ticks(symbol)))

        # Start candle streaming
        for symbol in self.symbols:
            for tf in self.timeframes:
                self._tasks.append(asyncio.create_task(self._stream_candles(symbol, tf)))

        # Start position/order streaming
        self._tasks.append(asyncio.create_task(self._stream_positions()))
        self._tasks.append(asyncio.create_task(self._stream_orders()))

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

        if self._redis:
            await self._redis.close()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, mt5.shutdown)

    # ── Symbol Management ─────────────────────────────────────────────────────

    async def _ensure_symbol(self, symbol: str) -> bool:
        """Ensure symbol is selected in Market Watch."""
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, mt5.symbol_info, symbol)
        if info is None:
            # Try to add to Market Watch
            await loop.run_in_executor(None, mt5.symbol_select, symbol, True)
            info = await loop.run_in_executor(None, mt5.symbol_info, symbol)
        if info:
            self._symbol_info_cache[symbol] = info
        return info is not None

    # ── Tick Streaming ────────────────────────────────────────────────────────

    async def _stream_ticks(self, symbol: str) -> None:
        """Stream real-time ticks from MT5."""
        while True:
            try:
                loop = asyncio.get_event_loop()
                tick = await loop.run_in_executor(None, mt5.symbol_info_tick, symbol)
                if tick:
                    await self._publish_tick(symbol, tick)
                await asyncio.sleep(0.1)  # 10Hz max
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Tick stream error for {symbol}: {e}")
                await asyncio.sleep(1)

    async def _publish_tick(self, symbol: str, tick: Any) -> None:
        """Publish MT5 tick to VPS Redis."""
        if not self._redis:
            return

        payload = {
            "type": "tick",
            "symbol": symbol,
            "bid": tick.bid,
            "ask": tick.ask,
            "last": tick.last,
            "volume": tick.volume,
            "time": tick.time,
            "flags": tick.flags,
            "timestamp": datetime.utcnow().isoformat(),
        }

        await self._redis.xadd("market:ticks", payload, maxlen=100000, approximate=True)

    # ── Candle Streaming ──────────────────────────────────────────────────────

    async def _stream_candles(self, symbol: str, timeframe: str) -> None:
        """Stream real-time candles from MT5."""
        mt5_timeframe = self._get_mt5_timeframe(timeframe)
        if mt5_timeframe is None:
            print(f"Unknown timeframe: {timeframe}")
            return

        while True:
            try:
                loop = asyncio.get_event_loop()
                rates = await loop.run_in_executor(
                    None,
                    lambda: mt5.copy_rates_from_pos(symbol, mt5_timeframe, 0, 2)
                )

                if rates is not None and len(rates) > 0:
                    latest = rates[-1]
                    candle_time = datetime.fromtimestamp(latest["time"])

                    # Only publish if new candle
                    key = f"{symbol}:{timeframe}"
                    if key not in self._last_candle_time or candle_time > self._last_candle_time[key]:
                        self._last_candle_time[key] = candle_time
                        await self._publish_candle(symbol, timeframe, latest)

                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Candle stream error for {symbol} {timeframe}: {e}")
                await asyncio.sleep(5)

    def _get_mt5_timeframe(self, timeframe: str) -> Optional[int]:
        """Map timeframe string to MT5 constant."""
        mapping = {
            "1m": mt5.TIMEFRAME_M1,
            "5m": mt5.TIMEFRAME_M5,
            "15m": mt5.TIMEFRAME_M15,
            "30m": mt5.TIMEFRAME_M30,
            "1h": mt5.TIMEFRAME_H1,
            "4h": mt5.TIMEFRAME_H4,
            "1d": mt5.TIMEFRAME_D1,
            "1w": mt5.TIMEFRAME_W1,
            "1M": mt5.TIMEFRAME_MN1,
        }
        return mapping.get(timeframe)

    async def _publish_candle(self, symbol: str, timeframe: str, rate: Dict) -> None:
        """Publish MT5 candle to VPS Redis."""
        if not self._redis:
            return

        payload = {
            "type": "candle",
            "symbol": symbol,
            "interval": timeframe,
            "open": rate["open"],
            "high": rate["high"],
            "low": rate["low"],
            "close": rate["close"],
            "tick_volume": rate["tick_volume"],
            "spread": rate["spread"],
            "real_volume": rate["real_volume"],
            "time": rate["time"],
            "timestamp": datetime.utcnow().isoformat(),
        }

        await self._redis.xadd("market:candles", payload, maxlen=100000, approximate=True)

    # ── Position/Order Streaming ──────────────────────────────────────────────

    async def _stream_positions(self) -> None:
        """Stream position updates."""
        last_positions = {}

        while True:
            try:
                loop = asyncio.get_event_loop()
                positions = await loop.run_in_executor(None, mt5.positions_get)

                if positions:
                    current = {p.ticket: p for p in positions}
                    # Detect changes
                    for ticket, pos in current.items():
                        if ticket not in last_positions or last_positions[ticket] != pos:
                            await self._publish_position_update(pos)
                    # Detect closed positions
                    for ticket in last_positions:
                        if ticket not in current:
                            await self._publish_position_closed(ticket, last_positions[ticket])

                    last_positions = current

                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Position stream error: {e}")
                await asyncio.sleep(5)

    async def _publish_position_update(self, pos: Any) -> None:
        if not self._redis:
            return

        payload = {
            "type": "position_update",
            "ticket": pos.ticket,
            "symbol": pos.symbol,
            "type": "buy" if pos.type == mt5.POSITION_TYPE_BUY else "sell",
            "volume": pos.volume,
            "price_open": pos.price_open,
            "price_current": pos.price_current,
            "sl": pos.sl,
            "tp": pos.tp,
            "profit": pos.profit,
            "swap": pos.swap,
            "margin": pos.margin,
            "timestamp": datetime.utcnow().isoformat(),
        }

        await self._redis.xadd("execution:positions", payload, maxlen=100000, approximate=True)

    async def _publish_position_closed(self, ticket: int, pos: Any) -> None:
        if not self._redis:
            return

        payload = {
            "type": "position_closed",
            "ticket": ticket,
            "symbol": pos.symbol,
            "profit": pos.profit,
            "timestamp": datetime.utcnow().isoformat(),
        }

        await self._redis.xadd("execution:positions", payload, maxlen=100000, approximate=True)

    async def _stream_orders(self) -> None:
        """Stream order updates."""
        last_orders = {}

        while True:
            try:
                loop = asyncio.get_event_loop()
                orders = await loop.run_in_executor(None, mt5.orders_get)

                if orders:
                    current = {o.ticket: o for o in orders}
                    for ticket, order in current.items():
                        if ticket not in last_orders or last_orders[ticket] != order:
                            await self._publish_order_update(order)
                    last_orders = current

                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Order stream error: {e}")
                await asyncio.sleep(5)

    async def _publish_order_update(self, order: Any) -> None:
        if not self._redis:
            return

        payload = {
            "type": "order_update",
            "ticket": order.ticket,
            "symbol": order.symbol,
            "type": self._map_order_type(order.type),
            "volume": order.volume_initial,
            "volume_current": order.volume_current,
            "price_open": order.price_open,
            "sl": order.sl,
            "tp": order.tp,
            "state": self._map_order_state(order.state),
            "timestamp": datetime.utcnow().isoformat(),
        }

        await self._redis.xadd("execution:orders", payload, maxlen=100000, approximate=True)

    def _map_order_type(self, mt5_type: int) -> str:
        mapping = {
            mt5.ORDER_TYPE_BUY: "market_buy",
            mt5.ORDER_TYPE_SELL: "market_sell",
            mt5.ORDER_TYPE_BUY_LIMIT: "limit_buy",
            mt5.ORDER_TYPE_SELL_LIMIT: "limit_sell",
            mt5.ORDER_TYPE_BUY_STOP: "stop_buy",
            mt5.ORDER_TYPE_SELL_STOP: "stop_sell",
            mt5.ORDER_TYPE_BUY_STOP_LIMIT: "stop_limit_buy",
            mt5.ORDER_TYPE_SELL_STOP_LIMIT: "stop_limit_sell",
        }
        return mapping.get(mt5_type, "unknown")

    def _map_order_state(self, mt5_state: int) -> str:
        mapping = {
            mt5.ORDER_STATE_STARTED: "started",
            mt5.ORDER_STATE_PLACED: "placed",
            mt5.ORDER_STATE_PARTIAL: "partial",
            mt5.ORDER_STATE_DONE: "done",
            mt5.ORDER_STATE_CANCELED: "canceled",
            mt5.ORDER_STATE_REJECTED: "rejected",
            mt5.ORDER_STATE_EXPIRED: "expired",
        }
        return mapping.get(mt5_state, "unknown")


async def run_mt5_bridge(
    login: int,
    password: str,
    server: str,
    redis_url: str = "redis://localhost:6379/0",
    symbols: Optional[List[str]] = None,
) -> None:
    """Entry point for running MT5 bridge as standalone script."""
    bridge = MT5Ingestion(
        login=login,
        password=password,
        server=server,
        redis_url=redis_url,
        symbols=symbols,
    )

    try:
        await bridge.connect()
        await bridge.start()
        # Keep running
        while True:
            await asyncio.sleep(60)
    except KeyboardInterrupt:
        print("Shutting down MT5 bridge...")
    finally:
        await bridge.stop()