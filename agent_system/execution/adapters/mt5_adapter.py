"""
MetaTrader 5 venue adapter implementation.
NOTE: This runs on Windows only (requires MetaTrader5 Python package).
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    mt5 = None

from execution.contracts import VenueAdapter, Venue, Order, Fill, Position, ExecutionIntent
from shared.domain import Instrument, OrderSide, OrderType, OrderStatus, TimeInForce, FillStatus, PositionSide


class MT5Adapter(VenueAdapter):
    """MetaTrader 5 adapter. Windows-only."""

    def __init__(
        self,
        login: int,
        password: str,
        server: str,
        path: Optional[str] = None,
    ):
        if not MT5_AVAILABLE:
            raise RuntimeError("MetaTrader5 package not available. This adapter requires Windows with MT5 installed.")
        self.login = login
        self.password = password
        self.server = server
        self.path = path
        self._connected = False
        self._symbol_info_cache: Dict[str, Any] = {}

    @property
    def venue(self) -> Venue:
        return Venue.MT5

    async def connect(self) -> bool:
        loop = asyncio.get_event_loop()
        self._connected = await loop.run_in_executor(
            None,
            lambda: mt5.initialize(
                login=self.login,
                password=self.password,
                server=self.server,
                path=self.path,
            )
        )
        if not self._connected:
            raise ConnectionError(f"MT5 init failed: {mt5.last_error()}")
        return True

    async def disconnect(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, mt5.shutdown)
        self._connected = False

    def normalize_symbol(self, canonical_symbol: str) -> str:
        # "BTC/USDT" -> "BTCUSDT" or broker-specific format
        return canonical_symbol.replace("/", "").replace("-", "")

    def denormalize_symbol(self, venue_symbol: str) -> str:
        # Heuristic split
        for quote in ["USD", "USDT", "USDC", "EUR", "GBP", "JPY"]:
            if venue_symbol.endswith(quote):
                base = venue_symbol[:-len(quote)]
                return f"{base}/{quote}"
        return venue_symbol

    async def _ensure_symbol(self, symbol: str) -> bool:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, mt5.symbol_info, symbol)
        if info is None:
            # Try to select in Market Watch
            await loop.run_in_executor(None, mt5.symbol_select, symbol, True)
            info = await loop.run_in_executor(None, mt5.symbol_info, symbol)
        if info:
            self._symbol_info_cache[symbol] = info
        return info is not None

    async def get_instrument_info(self, instrument: Instrument) -> Dict[str, Any]:
        venue_symbol = instrument.get_venue_symbol(self.venue)
        await self._ensure_symbol(venue_symbol)
        info = self._symbol_info_cache.get(venue_symbol)
        if info:
            return {
                "symbol": info.name,
                "tick_size": info.trade_tick_size,
                "lot_size": info.volume_step,
                "min_lot": info.volume_min,
                "max_lot": info.volume_max,
                "contract_size": info.trade_contract_size,
                "margin_initial": info.margin_initial,
                "margin_maintenance": info.margin_maintenance,
            }
        return {}

    async def submit_order(self, intent: ExecutionIntent) -> Order:
        if not self._connected:
            await self.connect()

        order = intent.order
        venue_symbol = self.normalize_symbol(order.instrument.symbol)

        await self._ensure_symbol(venue_symbol)

        # Map order type
        type_map = {
            OrderType.MARKET: mt5.ORDER_TYPE_BUY if order.side == OrderSide.BUY else mt5.ORDER_TYPE_SELL,
            OrderType.LIMIT: mt5.ORDER_TYPE_BUY_LIMIT if order.side == OrderSide.BUY else mt5.ORDER_TYPE_SELL_LIMIT,
            OrderType.STOP: mt5.ORDER_TYPE_BUY_STOP if order.side == OrderSide.BUY else mt5.ORDER_TYPE_SELL_STOP,
            OrderType.STOP_LIMIT: mt5.ORDER_TYPE_BUY_STOP_LIMIT if order.side == OrderSide.BUY else mt5.ORDER_TYPE_SELL_STOP_LIMIT,
        }

        request = {
            "action": mt5.TRADE_ACTION_DEAL if order.type == OrderType.MARKET else mt5.TRADE_ACTION_PENDING,
            "symbol": venue_symbol,
            "volume": float(order.quantity),
            "type": type_map.get(order.type, mt5.ORDER_TYPE_BUY),
            "price": float(order.price) if order.price else 0.0,
            "sl": float(order.stop_price) if order.stop_price else 0.0,
            "tp": float(order.take_profit) if order.take_profit else 0.0,
            "deviation": 20,
            "magic": 234000,
            "comment": f"strat:{intent.strategy_id}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, mt5.order_send, request)

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            raise Exception(f"MT5 order failed: {result.retcode} - {result.comment}")

        order.id = str(result.order)
        order.metadata["venue_order_id"] = str(result.order)
        order.metadata["deal_id"] = str(result.deal)
        order.status = OrderStatus.FILLED if order.type == OrderType.MARKET else OrderStatus.PENDING
        return order

    async def cancel_order(self, order_id: str) -> bool:
        loop = asyncio.get_event_loop()
        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": int(order_id),
        }
        result = await loop.run_in_executor(None, mt5.order_send, request)
        return result.retcode == mt5.TRADE_RETCODE_DONE

    async def get_order_status(self, order_id: str) -> Order:
        loop = asyncio.get_event_loop()
        orders = await loop.run_in_executor(None, mt5.orders_get, ticket=int(order_id))
        if not orders:
            return Order(id=order_id, status=OrderStatus.REJECTED)
        o = orders[0]
        status_map = {
            mt5.ORDER_STATE_STARTED: OrderStatus.PENDING,
            mt5.ORDER_STATE_PLACED: OrderStatus.PENDING,
            mt5.ORDER_STATE_PARTIAL: OrderStatus.PARTIALLY_FILLED,
            mt5.ORDER_STATE_DONE: OrderStatus.FILLED,
            mt5.ORDER_STATE_CANCELED: OrderStatus.CANCELLED,
            mt5.ORDER_STATE_REJECTED: OrderStatus.REJECTED,
            mt5.ORDER_STATE_EXPIRED: OrderStatus.CANCELLED,
        }
        return Order(
            id=order_id,
            status=status_map.get(o.state, OrderStatus.PENDING),
            filled_quantity=Decimal(str(o.volume_current)),
        )

    async def get_positions(self) -> List[Position]:
        loop = asyncio.get_event_loop()
        positions = await loop.run_in_executor(None, mt5.positions_get)
        result = []
        if positions:
            for p in positions:
                instrument = Instrument(symbol=self.denormalize_symbol(p.symbol))
                side = PositionSide.LONG if p.type == mt5.POSITION_TYPE_BUY else PositionSide.SHORT
                result.append(Position(
                    strategy_id=str(p.magic),
                    instrument=instrument,
                    venue=self.venue,
                    side=side,
                    quantity=Decimal(str(p.volume)),
                    entry_price=Decimal(str(p.price_open)),
                    current_price=Decimal(str(p.price_current)),
                    unrealized_pnl=Decimal(str(p.profit)),
                    margin_used=Decimal(str(p.margin)),
                    leverage=Decimal("1"),
                ))
        return result

    async def get_fills(self, since: Optional[datetime] = None) -> List[Fill]:
        loop = asyncio.get_event_loop()
        from_date = since if since else datetime(1970, 1, 1)
        deals = await loop.run_in_executor(None, mt5.history_deals_get, from_date, datetime.now())
        fills = []
        if deals:
            for d in deals:
                instrument = Instrument(symbol=self.denormalize_symbol(d.symbol))
                side = OrderSide.BUY if d.type == mt5.DEAL_TYPE_BUY else OrderSide.SELL
                fills.append(Fill(
                    order_id=str(d.order),
                    strategy_id=str(d.magic),
                    instrument=instrument,
                    venue=self.venue,
                    side=side,
                    quantity=Decimal(str(d.volume)),
                    price=Decimal(str(d.price)),
                    commission=Decimal(str(d.commission)),
                    timestamp=datetime.fromtimestamp(d.time),
                ))
        return fills

    async def get_balances(self) -> Dict[str, Decimal]:
        loop = asyncio.get_event_loop()
        account = await loop.run_in_executor(None, mt5.account_info)
        if account:
            return {
                "balance": Decimal(str(account.balance)),
                "equity": Decimal(str(account.equity)),
                "margin": Decimal(str(account.margin)),
                "free_margin": Decimal(str(account.margin_free)),
            }
        return {}

    async def reconcile_positions(self, our_positions: List[Position]) -> List[Dict[str, Any]]:
        venue_positions = await self.get_positions()
        discrepancies = []
        venue_map = {f"{p.instrument.symbol}:{p.venue.value}": p for p in venue_positions}
        for ours in our_positions:
            key = f"{ours.instrument.symbol}:{ours.venue.value}"
            if key not in venue_map:
                discrepancies.append({"type": "missing_on_venue", "our_position": ours})
            else:
                theirs = venue_map[key]
                if abs(ours.quantity - theirs.quantity) > Decimal("0.0001"):
                    discrepancies.append({"type": "quantity_mismatch", "ours": ours, "theirs": theirs})
        return discrepancies

    async def reconcile_fills(self, our_fills: List[Fill], since: datetime) -> List[Dict[str, Any]]:
        venue_fills = await self.get_fills(since)
        discrepancies = []
        return discrepancies

    async def calculate_margin_requirement(self, position: Position) -> Decimal:
        await self._ensure_symbol(position.instrument.get_venue_symbol(self.venue))
        info = self._symbol_info_cache.get(position.instrument.get_venue_symbol(self.venue))
        if info:
            return Decimal(str(info.margin_initial)) * position.quantity
        return position.margin_used

    async def calculate_fees(self, order: Order) -> Decimal:
        # MT5 fees vary by broker - estimate
        return Decimal("0")


from execution.contracts import adapter_registry
# MT5 adapter registered at runtime when available