"""
Canonical Normalizer — converts venue-specific payloads to canonical domain models.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from shared.domain import (
    Instrument,
    MarketData,
    Order,
    Fill,
    Position,
    Signal,
    ExecutionIntent,
    Venue,
    OrderSide,
    OrderType,
    TimeInForce,
    OrderStatus,
    FillStatus,
    PositionSide,
)


class CanonicalNormalizer:
    """
    Converts venue-specific payloads into canonical domain models.
    Each venue adapter should use this to normalize before publishing.
    """

    def __init__(self):
        self._instrument_cache: Dict[str, Instrument] = {}

    # ── Instrument ─────────────────────────────────────────────────────────────

    def normalize_instrument(
        self,
        venue: Venue,
        venue_symbol: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Instrument:
        """Create or retrieve canonical instrument from venue symbol."""
        cache_key = f"{venue.value}:{venue_symbol}"
        if cache_key in self._instrument_cache:
            return self._instrument_cache[cache_key]

        # Parse base/quote from venue symbol
        base, quote = self._parse_symbol(venue, venue_symbol)

        instrument = Instrument(
            symbol=f"{base}/{quote}",
            base=base,
            quote=quote,
            venue_symbol_map={venue: venue_symbol},
            contract_size=Decimal(str(metadata.get("contract_size", 1))) if metadata else Decimal("1"),
            tick_size=Decimal(str(metadata.get("tick_size", "0.01"))) if metadata else Decimal("0.01"),
            lot_size=Decimal(str(metadata.get("lot_size", 1))) if metadata else Decimal("1"),
            min_notional=Decimal(str(metadata.get("min_notional"))) if metadata and metadata.get("min_notional") else None,
            max_leverage=Decimal(str(metadata.get("max_leverage"))) if metadata and metadata.get("max_leverage") else None,
            metadata=metadata or {},
        )

        self._instrument_cache[cache_key] = instrument
        return instrument

    def _parse_symbol(self, venue: Venue, symbol: str) -> tuple[str, str]:
        """Parse base/quote from venue-specific symbol format."""
        # Delta: BTCUSDT -> BTC/USDT
        if venue == Venue.DELTA:
            for quote in ["USDT", "USDC", "BTC", "ETH", "USDT"]:
                if symbol.endswith(quote):
                    return symbol[:-len(quote)], quote
        # MT5: varies by broker, try common patterns
        elif venue == Venue.MT5:
            for quote in ["USD", "USDT", "USDC", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF"]:
                if symbol.endswith(quote):
                    return symbol[:-len(quote)], quote
        # Binance: BTCUSDT -> BTC/USDT
        elif venue == Venue.BINANCE:
            for quote in ["USDT", "USDC", "BTC", "ETH", "BUSD", "FDUSD"]:
                if symbol.endswith(quote):
                    return symbol[:-len(quote)], quote

        # Fallback: split in middle
        mid = len(symbol) // 2
        return symbol[:mid], symbol[mid:]

    # ── Market Data ────────────────────────────────────────────────────────────

    def normalize_tick(
        self,
        venue: Venue,
        venue_symbol: str,
        payload: Dict[str, Any],
        timestamp: Optional[datetime] = None,
    ) -> MarketData:
        """Normalize a tick/price update to canonical MarketData."""
        instrument = self.normalize_instrument(venue, venue_symbol)

        return MarketData(
            instrument=instrument,
            venue=venue,
            timestamp=timestamp or datetime.utcnow(),
            bid_price=self._to_decimal(payload.get("bid_price") or payload.get("bid") or payload.get("b")),
            ask_price=self._to_decimal(payload.get("ask_price") or payload.get("ask") or payload.get("a")),
            bid_size=self._to_decimal(payload.get("bid_size") or payload.get("bid_volume") or payload.get("bv")),
            ask_size=self._to_decimal(payload.get("ask_size") or payload.get("ask_volume") or payload.get("av")),
            last_price=self._to_decimal(payload.get("last_price") or payload.get("last") or payload.get("c")),
            last_size=self._to_decimal(payload.get("last_size") or payload.get("volume") or payload.get("v")),
            is_candle=False,
        )

    def normalize_candle(
        self,
        venue: Venue,
        venue_symbol: str,
        payload: Dict[str, Any],
        interval: str,
        timestamp: Optional[datetime] = None,
    ) -> MarketData:
        """Normalize a candle/OHLCV to canonical MarketData."""
        instrument = self.normalize_instrument(venue, venue_symbol)

        return MarketData(
            instrument=instrument,
            venue=venue,
            timestamp=timestamp or datetime.utcnow(),
            open=self._to_decimal(payload.get("open") or payload.get("o")),
            high=self._to_decimal(payload.get("high") or payload.get("h")),
            low=self._to_decimal(payload.get("low") or payload.get("l")),
            close=self._to_decimal(payload.get("close") or payload.get("c")),
            volume=self._to_decimal(payload.get("volume") or payload.get("v")),
            interval=interval,
            is_candle=True,
        )

    # ── Orders ──────────────────────────────────────────────────────────────────

    def normalize_order(
        self,
        venue: Venue,
        venue_symbol: str,
        payload: Dict[str, Any],
        strategy_id: str,
    ) -> Order:
        """Normalize venue order to canonical Order."""
        instrument = self.normalize_instrument(venue, venue_symbol)

        return Order(
            id=payload.get("id", payload.get("order_id", "")),
            client_order_id=payload.get("client_order_id"),
            strategy_id=strategy_id,
            instrument=instrument,
            venue=venue,
            side=self._parse_side(payload.get("side")),
            type=self._parse_order_type(payload.get("type", payload.get("order_type"))),
            quantity=self._to_decimal(payload.get("size") or payload.get("quantity") or payload.get("qty")),
            price=self._to_decimal(payload.get("price") or payload.get("limit_price")),
            stop_price=self._to_decimal(payload.get("stop_price") or payload.get("trigger_price")),
            time_in_force=self._parse_tif(payload.get("time_in_force", payload.get("tif"))),
            status=self._parse_order_status(payload.get("status", payload.get("state"))),
            filled_quantity=self._to_decimal(payload.get("filled_size") or payload.get("filled_qty") or payload.get("filled_quantity")),
            average_fill_price=self._to_decimal(payload.get("average_fill_price") or payload.get("avg_price")),
            commission=self._to_decimal(payload.get("commission") or payload.get("fee")),
            metadata=payload,
        )

    # ── Fills ───────────────────────────────────────────────────────────────────

    def normalize_fill(
        self,
        venue: Venue,
        venue_symbol: str,
        payload: Dict[str, Any],
        strategy_id: str,
    ) -> Fill:
        """Normalize venue fill to canonical Fill."""
        instrument = self.normalize_instrument(venue, venue_symbol)

        return Fill(
            id=payload.get("id", payload.get("fill_id", "")),
            order_id=payload.get("order_id", ""),
            strategy_id=strategy_id,
            instrument=instrument,
            venue=venue,
            side=self._parse_side(payload.get("side")),
            quantity=self._to_decimal(payload.get("size") or payload.get("qty")),
            price=self._to_decimal(payload.get("price")),
            commission=self._to_decimal(payload.get("commission") or payload.get("fee")),
            commission_currency=payload.get("commission_currency", "USDT"),
            timestamp=self._parse_timestamp(payload.get("timestamp") or payload.get("time")),
            status=self._parse_fill_status(payload.get("status")),
            liquidity=payload.get("liquidity"),
            metadata=payload,
        )

    # ── Positions ───────────────────────────────────────────────────────────────

    def normalize_position(
        self,
        venue: Venue,
        venue_symbol: str,
        payload: Dict[str, Any],
        strategy_id: str,
    ) -> Position:
        """Normalize venue position to canonical Position."""
        instrument = self.normalize_instrument(venue, venue_symbol)

        qty = self._to_decimal(payload.get("size") or payload.get("quantity") or payload.get("qty"))
        side = PositionSide.LONG if qty >= 0 else PositionSide.SHORT

        return Position(
            id=payload.get("id", ""),
            strategy_id=strategy_id,
            instrument=instrument,
            venue=venue,
            side=side,
            quantity=abs(qty),
            entry_price=self._to_decimal(payload.get("entry_price") or payload.get("avg_entry_price")),
            current_price=self._to_decimal(payload.get("mark_price") or payload.get("current_price")),
            unrealized_pnl=self._to_decimal(payload.get("unrealized_pnl") or payload.get("unrealised_pnl")),
            realized_pnl=self._to_decimal(payload.get("realized_pnl") or payload.get("realised_pnl")),
            margin_used=self._to_decimal(payload.get("margin") or payload.get("initial_margin")),
            leverage=self._to_decimal(payload.get("leverage", 1)),
            metadata=payload,
        )

    # ── Helpers ─────────────────────────────────────────────────────────────────

    def _to_decimal(self, value: Any) -> Optional[Decimal]:
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None

    def _parse_side(self, value: Any) -> OrderSide:
        if not value:
            return OrderSide.BUY
        v = str(value).lower()
        if v in ("buy", "b", "long", "1"):
            return OrderSide.BUY
        return OrderSide.SELL

    def _parse_order_type(self, value: Any) -> OrderType:
        if not value:
            return OrderType.MARKET
        v = str(value).lower()
        if v in ("limit", "l"):
            return OrderType.LIMIT
        elif v in ("stop", "stop_market", "sl"):
            return OrderType.STOP
        elif v in ("stop_limit", "sl_limit"):
            return OrderType.STOP_LIMIT
        return OrderType.MARKET

    def _parse_tif(self, value: Any) -> TimeInForce:
        if not value:
            return TimeInForce.GTC
        v = str(value).lower()
        if v in ("ioc", "immediate_or_cancel"):
            return TimeInForce.IOC
        elif v in ("fok", "fill_or_kill"):
            return TimeInForce.FOK
        elif v in ("gtd", "good_till_date"):
            return TimeInForce.GTD
        return TimeInForce.GTC

    def _parse_order_status(self, value: Any) -> OrderStatus:
        if not value:
            return OrderStatus.NEW
        v = str(value).lower()
        if v in ("new", "pending", "open", "active"):
            return OrderStatus.NEW
        elif v in ("partially_filled", "partial", "partially_filled"):
            return OrderStatus.PARTIALLY_FILLED
        elif v in ("filled", "done", "complete", "closed"):
            return OrderStatus.FILLED
        elif v in ("cancelled", "canceled", "cancel"):
            return OrderStatus.CANCELLED
        elif v in ("rejected", "reject"):
            return OrderStatus.REJECTED
        return OrderStatus.NEW

    def _parse_fill_status(self, value: Any) -> FillStatus:
        if not value:
            return FillStatus.FILLED
        v = str(value).lower()
        if v in ("partial", "partially_filled"):
            return FillStatus.PARTIAL
        elif v in ("rejected", "reject"):
            return FillStatus.REJECTED
        return FillStatus.FILLED

    def _parse_timestamp(self, value: Any) -> datetime:
        if not value:
            return datetime.utcnow()
        if isinstance(value, (int, float)):
            # Assume milliseconds if large, seconds if small
            if value > 1e12:
                return datetime.fromtimestamp(value / 1000)
            return datetime.fromtimestamp(value)
        if isinstance(value, str):
            for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        return datetime.utcnow()


# Global normalizer instance
_normalizer: Optional[CanonicalNormalizer] = None


def get_normalizer() -> CanonicalNormalizer:
    global _normalizer
    if _normalizer is None:
        _normalizer = CanonicalNormalizer()
    return _normalizer