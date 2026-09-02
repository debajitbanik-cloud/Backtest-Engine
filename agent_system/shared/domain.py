"""
Canonical domain models — venue-agnostic definitions for the trading system.

This module defines the single source of truth for all core trading concepts:
Instrument, MarketData, Order, Fill, Position, Signal, ExecutionIntent,
StrategyIdentity, and their associated enums.

All venue-specific adapters (Delta, MT5, etc.) must normalize their payloads
into these canonical types before publishing to the event backbone.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ── Enums ──────────────────────────────────────────────────────────────────────

class Venue(str, Enum):
    """Execution venue identifiers."""
    DELTA = "delta"
    MT5 = "mt5"
    BINANCE = "binance"
    SYNTHETIC = "synthetic"  # for backtests


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TimeInForce(str, Enum):
    GTC = "gtc"      # Good Till Cancelled
    IOC = "ioc"      # Immediate Or Cancel
    FOK = "fok"      # Fill Or Kill
    GTD = "gtd"      # Good Till Date


class OrderStatus(str, Enum):
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    PENDING = "pending"


class FillStatus(str, Enum):
    FILLED = "filled"
    PARTIAL = "partial"
    REJECTED = "rejected"


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class SignalType(str, Enum):
    ENTRY = "entry"
    EXIT = "exit"
    ADJUST = "adjust"
    HEDGE = "hedge"
    CLOSE_ALL = "close_all"


# ── Core Domain Models ─────────────────────────────────────────────────────────


class Instrument(BaseModel):
    """
    Venue-agnostic instrument definition.
    Uniquely identifies a tradable asset across all venues.
    """
    symbol: str = Field(..., description="Canonical symbol, e.g. 'BTC/USDT'")
    base: str = Field(..., description="Base currency, e.g. 'BTC'")
    quote: str = Field(..., description="Quote currency, e.g. 'USDT'")
    venue_symbol_map: Dict[Venue, str] = Field(
        default_factory=dict,
        description="Venue-specific symbol mappings"
    )
    contract_size: Decimal = Field(
        default=Decimal("1"),
        description="Contract multiplier (futures/options)"
    )
    tick_size: Decimal = Field(
        default=Decimal("0.01"),
        description="Minimum price increment"
    )
    lot_size: Decimal = Field(
        default=Decimal("1"),
        description="Minimum order quantity"
    )
    min_notional: Optional[Decimal] = Field(
        default=None,
        description="Minimum notional value for orders"
    )
    max_leverage: Optional[Decimal] = Field(
        default=None,
        description="Maximum allowed leverage"
    )
    is_active: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("contract_size", "tick_size", "lot_size", "min_notional", "max_leverage", mode="before")
    @classmethod
    def _to_decimal(cls, v):
        if v is None:
            return None
        return Decimal(str(v))

    def get_venue_symbol(self, venue: Venue) -> str:
        return self.venue_symbol_map.get(venue, self.symbol)

    def __hash__(self):
        return hash(self.symbol)


class MarketData(BaseModel):
    """Canonical market data point (tick or candle)."""
    instrument: Instrument
    venue: Venue
    timestamp: datetime
    # Tick fields
    bid_price: Optional[Decimal] = None
    ask_price: Optional[Decimal] = None
    bid_size: Optional[Decimal] = None
    ask_size: Optional[Decimal] = None
    last_price: Optional[Decimal] = None
    last_size: Optional[Decimal] = None
    # Candle fields (if this is a candle)
    open: Optional[Decimal] = None
    high: Optional[Decimal] = None
    low: Optional[Decimal] = None
    close: Optional[Decimal] = None
    volume: Optional[Decimal] = None
    # Metadata
    interval: Optional[str] = None  # e.g. "1m", "5m", "1h" for candles
    sequence: Optional[int] = None
    is_candle: bool = False

    @field_validator("bid_price", "ask_price", "bid_size", "ask_size",
                     "last_price", "last_size", "open", "high", "low", "close", "volume", mode="before")
    @classmethod
    def _to_decimal(cls, v):
        if v is None:
            return None
        return Decimal(str(v))


class Order(BaseModel):
    """Canonical order representation."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_order_id: Optional[str] = None
    strategy_id: str
    instrument: Instrument
    venue: Venue
    side: OrderSide
    type: OrderType = OrderType.MARKET
    quantity: Decimal
    price: Optional[Decimal] = None  # for limit/stop orders
    stop_price: Optional[Decimal] = None  # for stop orders
    time_in_force: TimeInForce = TimeInForce.GTC
    status: OrderStatus = OrderStatus.NEW
    filled_quantity: Decimal = Decimal("0")
    average_fill_price: Optional[Decimal] = None
    commission: Decimal = Decimal("0")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("quantity", "price", "stop_price", "filled_quantity", "average_fill_price", "commission", mode="before")
    @classmethod
    def _to_decimal(cls, v):
        if v is None:
            return None
        return Decimal(str(v))

    @property
    def remaining_quantity(self) -> Decimal:
        return self.quantity - self.filled_quantity

    @property
    def is_active(self) -> bool:
        return self.status in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED, OrderStatus.PENDING)


class Fill(BaseModel):
    """Canonical fill/trade execution."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order_id: str
    strategy_id: str
    instrument: Instrument
    venue: Venue
    side: OrderSide
    quantity: Decimal
    price: Decimal
    commission: Decimal = Decimal("0")
    commission_currency: str = "USDT"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: FillStatus = FillStatus.FILLED
    liquidity: Optional[str] = None  # "maker" or "taker"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("quantity", "price", "commission", mode="before")
    @classmethod
    def _to_decimal(cls, v):
        if v is None:
            return None
        return Decimal(str(v))

    @property
    def notional(self) -> Decimal:
        return self.quantity * self.price


class Position(BaseModel):
    """Canonical position state."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    strategy_id: str
    instrument: Instrument
    venue: Venue
    side: PositionSide
    quantity: Decimal
    entry_price: Decimal
    current_price: Optional[Decimal] = None
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    margin_used: Decimal = Decimal("0")
    leverage: Decimal = Decimal("1")
    opened_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("quantity", "entry_price", "current_price", "unrealized_pnl", "realized_pnl", "margin_used", "leverage", mode="before")
    @classmethod
    def _to_decimal(cls, v):
        if v is None:
            return None
        return Decimal(str(v))

    def update_price(self, price: Decimal) -> None:
        self.current_price = price
        if self.side == PositionSide.LONG:
            self.unrealized_pnl = (price - self.entry_price) * self.quantity
        else:
            self.unrealized_pnl = (self.entry_price - price) * self.quantity
        self.updated_at = datetime.utcnow()


class Signal(BaseModel):
    """Canonical trading signal."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    strategy_id: str
    instrument: Instrument
    signal_type: SignalType
    side: Optional[OrderSide] = None
    quantity: Optional[Decimal] = None
    price: Optional[Decimal] = None  # target price
    stop_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None
    confidence: Decimal = Decimal("0.5")  # 0-1
    reasoning: str = ""
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("quantity", "price", "stop_price", "take_profit_price", "confidence", mode="before")
    @classmethod
    def _to_decimal(cls, v):
        if v is None:
            return None
        return Decimal(str(v))


class ExecutionIntent(BaseModel):
    """
    Bridge between signal generation and venue-specific execution.
    Created by Risk Overlay from a Signal.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: str
    strategy_id: str
    instrument: Instrument
    venue: Venue
    order: Order  # the order to be executed
    risk_checks_passed: bool = False
    risk_notes: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StrategyIdentity(BaseModel):
    """Strategy identifier with versioning."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    version: str  # semantic version, e.g. "1.2.0"
    description: str = ""
    parameters: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def full_id(self) -> str:
        return f"{self.name}:{self.version}"

    def __hash__(self):
        return hash(self.id)