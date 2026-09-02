"""
Delta Exchange venue adapter implementation.
"""
from __future__ import annotations

import asyncio
import hmac
import hashlib
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import aiohttp

from execution.contracts import VenueAdapter, Venue, Order, Fill, Position, ExecutionIntent
from shared.domain import Instrument, OrderSide, OrderType, OrderStatus, TimeInForce, FillStatus, PositionSide


class DeltaAdapter(VenueAdapter):
    """Delta Exchange (India) REST + WebSocket adapter."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = "https://api.india.delta.exchange",
        ws_url: str = "wss://socket.delta.exchange",
        testnet: bool = True,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.ws_url = ws_url
        self.testnet = testnet
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._instrument_cache: Dict[str, Dict] = {}

    @property
    def venue(self) -> Venue:
        return Venue.DELTA

    def _generate_signature(self, method: str, endpoint: str, payload: str = "") -> tuple[str, str]:
        timestamp = str(int(time.time()))
        signature_data = f"{method}{timestamp}{endpoint}{payload}"
        signature = hmac.new(
            self.api_secret.encode(),
            signature_data.encode(),
            hashlib.sha256
        ).hexdigest()
        return timestamp, signature

    async def _request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Dict] = None,
        authenticated: bool = False,
    ) -> Dict:
        if self._session is None:
            self._session = aiohttp.ClientSession()

        url = f"{self.base_url}{endpoint}"
        headers = {"Content-Type": "application/json"}

        if authenticated:
            timestamp, signature = self._generate_signature(method, endpoint, json.dumps(payload or {}))
            headers.update({
                "api-key": self.api_key,
                "signature": signature,
                "timestamp": timestamp,
            })

        import json
        async with self._session.request(method, url, json=payload, headers=headers) as resp:
            data = await resp.json()
            if not data.get("success", True):
                raise Exception(f"Delta API error: {data.get('error', 'Unknown error')}")
            return data

    async def connect(self) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        # Fetch instrument metadata
        await self._load_instruments()

    async def disconnect(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        if self._ws and not self._ws.closed:
            await self._ws.close()

    async def _load_instruments(self) -> None:
        data = await self._request("GET", "/v2/products")
        for product in data.get("result", []):
            self._instrument_cache[product["symbol"]] = product

    def normalize_symbol(self, canonical_symbol: str) -> str:
        # Canonical "BTC/USDT" -> Delta "BTCUSDT"
        return canonical_symbol.replace("/", "").replace("-", "")

    def denormalize_symbol(self, venue_symbol: str) -> str:
        # Delta "BTCUSDT" -> canonical "BTC/USDT"
        # Heuristic: split at known quote currencies
        for quote in ["USDT", "USDC", "BTC", "ETH"]:
            if venue_symbol.endswith(quote):
                base = venue_symbol[:-len(quote)]
                return f"{base}/{quote}"
        return venue_symbol

    async def get_instrument_info(self, instrument: Instrument) -> Dict[str, Any]:
        venue_symbol = instrument.get_venue_symbol(self.venue)
        if venue_symbol not in self._instrument_cache:
            await self._load_instruments()
        return self._instrument_cache.get(venue_symbol, {})

    async def submit_order(self, intent: ExecutionIntent) -> Order:
        order = intent.order
        venue_symbol = self.normalize_symbol(instrument.symbol for instrument in [intent.instrument])[0]

        payload = {
            "product_symbol": venue_symbol,
            "order_type": order.type.value,
            "side": order.side.value,
            "size": int(order.quantity),
            "time_in_force": order.time_in_force.value,
        }

        if order.type in (OrderType.LIMIT, OrderType.STOP_LIMIT):
            payload["limit_price"] = str(order.price)
        if order.type in (OrderType.STOP, OrderType.STOP_LIMIT):
            payload["stop_price"] = str(order.stop_price)

        data = await self._request("POST", "/v2/orders", payload, authenticated=True)

        result = data.get("result", {})
        order.id = result.get("id", order.id)
        order.status = OrderStatus.PENDING
        order.metadata["venue_order_id"] = result.get("id")
        order.metadata["client_order_id"] = result.get("client_order_id")
        return order

    async def cancel_order(self, order_id: str) -> bool:
        data = await self._request("DELETE", f"/v2/orders/{order_id}", authenticated=True)
        return data.get("success", False)

    async def get_order_status(self, order_id: str) -> Order:
        data = await self._request("GET", f"/v2/orders/{order_id}", authenticated=True)
        result = data.get("result", {})
        # Map to canonical Order
        # (implementation details omitted for brevity)
        return Order(
            id=order_id,
            status=OrderStatus(result.get("state", "pending")),
            filled_quantity=Decimal(str(result.get("filled_size", 0))),
            average_fill_price=Decimal(str(result.get("average_fill_price", 0))) if result.get("average_fill_price") else None,
        )

    async def get_positions(self) -> List[Position]:
        data = await self._request("GET", "/v2/positions", authenticated=True)
        positions = []
        for p in data.get("result", []):
            instrument = Instrument(symbol=self.denormalize_symbol(p["product_symbol"]))
            side = PositionSide.LONG if p["size"] > 0 else PositionSide.SHORT
            positions.append(Position(
                strategy_id=p.get("strategy_id", "unknown"),
                instrument=instrument,
                venue=self.venue,
                side=side,
                quantity=Decimal(str(abs(p["size"]))),
                entry_price=Decimal(str(p["entry_price"])),
                current_price=Decimal(str(p.get("mark_price", p["entry_price"]))),
                unrealized_pnl=Decimal(str(p.get("unrealized_pnl", 0))),
                realized_pnl=Decimal(str(p.get("realized_pnl", 0))),
                margin_used=Decimal(str(p.get("margin", 0))),
                leverage=Decimal(str(p.get("leverage", 1))),
            ))
        return positions

    async def get_fills(self, since: Optional[datetime] = None) -> List[Fill]:
        params = {}
        if since:
            params["start_time"] = int(since.timestamp())
        data = await self._request("GET", "/v2/fills", params=params, authenticated=True)
        fills = []
        for f in data.get("result", []):
            instrument = Instrument(symbol=self.denormalize_symbol(f["product_symbol"]))
            side = OrderSide.BUY if f["side"] == "buy" else OrderSide.SELL
            fills.append(Fill(
                order_id=f.get("order_id", ""),
                strategy_id=f.get("strategy_id", "unknown"),
                instrument=instrument,
                venue=self.venue,
                side=side,
                quantity=Decimal(str(f["size"])),
                price=Decimal(str(f["price"])),
                commission=Decimal(str(f.get("fee", 0))),
                timestamp=datetime.fromtimestamp(f["timestamp"]),
            ))
        return fills

    async def get_balances(self) -> Dict[str, Decimal]:
        data = await self._request("GET", "/v2/wallet/balances", authenticated=True)
        balances = {}
        for b in data.get("result", []):
            balances[b["asset_symbol"]] = Decimal(str(b["available_balance"]))
        return balances

    async def reconcile_positions(self, our_positions: List[Position]) -> List[Dict[str, Any]]:
        venue_positions = await self.get_positions()
        discrepancies = []
        # Simple reconciliation logic
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
        # Match by order_id + timestamp + quantity
        discrepancies = []
        # (implementation details omitted)
        return discrepancies

    async def calculate_margin_requirement(self, position: Position) -> Decimal:
        info = await self.get_instrument_info(position.instrument)
        margin_rate = Decimal(str(info.get("initial_margin_rate", "0.05")))
        return position.quantity * position.current_price * margin_rate

    async def calculate_fees(self, order: Order) -> Decimal:
        # Delta fee structure: 0.02% maker, 0.05% taker
        notional = order.quantity * (order.price or Decimal("0"))
        return notional * Decimal("0.0005")  # taker fee estimate


from execution.contracts import adapter_registry
adapter_registry.register(DeltaAdapter(
    api_key="",  # Will be set at runtime
    api_secret="",
))