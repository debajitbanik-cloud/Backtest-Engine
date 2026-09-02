"""
Execution plane contracts: Signal -> Risk Overlay -> ExecutionIntent -> VenueAdapter.

Defines the canonical interfaces that all venue adapters must implement.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from shared.domain import (
    Instrument,
    Order,
    Fill,
    Position,
    Signal,
    ExecutionIntent,
    Venue,
    OrderStatus,
    OrderSide,
)


# ── Risk Overlay ──────────────────────────────────────────────────────────────

@dataclass
class RiskCheckResult:
    """Result of a risk check on a signal/intent."""
    passed: bool
    checks: Dict[str, bool]
    notes: List[str]
    adjusted_quantity: Optional[Decimal] = None
    adjusted_price: Optional[Decimal] = None
    adjusted_stop: Optional[Decimal] = None
    adjusted_take_profit: Optional[Decimal] = None


class RiskOverlay(ABC):
    """
    Abstract risk overlay that evaluates signals/intentions against
    portfolio risk limits before they become execution intents.
    """

    @abstractmethod
    async def evaluate_signal(self, signal: Signal, portfolio_state: PortfolioState) -> RiskCheckResult:
        """Evaluate a raw signal against risk rules."""
        pass

    @abstractmethod
    async def evaluate_intent(self, intent: ExecutionIntent, portfolio_state: PortfolioState) -> RiskCheckResult:
        """Evaluate an execution intent (after signal processing)."""
        pass


@dataclass
class PortfolioState:
    """Current portfolio state for risk evaluation."""
    positions: Dict[str, Position]  # key: instrument symbol
    total_equity: Decimal
    available_margin: Decimal
    used_margin: Decimal
    daily_pnl: Decimal
    open_orders: List[Order]
    risk_limits: RiskLimits


@dataclass
class RiskLimits:
    """Configurable risk limits."""
    max_portfolio_drawdown: Decimal = Decimal("0.10")
    max_daily_loss: Decimal = Decimal("0.03")
    max_position_size_pct: Decimal = Decimal("0.20")
    max_sector_exposure: Decimal = Decimal("0.40")
    max_leverage: Decimal = Decimal("20.0")
    max_hold_time_losing_hours: int = 24
    max_consecutive_losses: int = 5
    loss_streak_reduction: Decimal = Decimal("0.5")
    margin_warning: Decimal = Decimal("0.70")
    margin_critical: Decimal = Decimal("0.85")
    margin_liquidation: Decimal = Decimal("0.95")
    max_portfolio_volatility: Decimal = Decimal("0.05")
    var_confidence: Decimal = Decimal("0.95")
    var_horizon_days: int = 1
    max_correlation: Decimal = Decimal("0.7")
    auto_mitigate: bool = True


# ── Venue Adapter Interface ───────────────────────────────────────────────────

class VenueAdapter(ABC):
    """
    Abstract base for venue-specific execution adapters.
    Each venue (Delta, MT5, etc.) implements this interface.
    """

    @property
    @abstractmethod
    def venue(self) -> Venue:
        """Return the venue this adapter handles."""
        pass

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the venue."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the venue."""
        pass

    @abstractmethod
    async def submit_order(self, intent: ExecutionIntent) -> Order:
        """Submit an order to the venue. Returns the order with venue order ID."""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order by venue order ID."""
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str) -> Order:
        """Get current status of an order."""
        pass

    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """Get all current positions."""
        pass

    @abstractmethod
    async def get_fills(self, since: Optional[datetime] = None) -> List[Fill]:
        """Get recent fills."""
        pass

    @abstractmethod
    async def get_balances(self) -> Dict[str, Decimal]:
        """Get account balances."""
        pass

    @abstractmethod
    async def get_instrument_info(self, instrument: Instrument) -> Dict[str, Any]:
        """Get venue-specific instrument details (tick size, lot size, etc.)."""
        pass

    # ── Reconciliation ──────────────────────────────────────────────────────

    @abstractmethod
    async def reconcile_positions(self, our_positions: List[Position]) -> List[Dict[str, Any]]:
        """Compare our position state with venue's and return discrepancies."""
        pass

    @abstractmethod
    async def reconcile_fills(self, our_fills: List[Fill], since: datetime) -> List[Dict[str, Any]]:
        """Compare our fill history with venue's."""
        pass

    # ── Venue-specific calculations ─────────────────────────────────────────

    @abstractmethod
    async def calculate_margin_requirement(self, position: Position) -> Decimal:
        """Calculate margin required for a position."""
        pass

    @abstractmethod
    async def calculate_fees(self, order: Order) -> Decimal:
        """Calculate estimated fees for an order."""
        pass

    @abstractmethod
    def normalize_symbol(self, canonical_symbol: str) -> str:
        """Convert canonical symbol to venue-specific symbol."""
        pass

    @abstractmethod
    def denormalize_symbol(self, venue_symbol: str) -> str:
        """Convert venue-specific symbol to canonical."""
        pass


# ── Adapter Registry ──────────────────────────────────────────────────────────

class AdapterRegistry:
    """Registry of venue adapters."""

    def __init__(self):
        self._adapters: Dict[Venue, VenueAdapter] = {}

    def register(self, adapter: VenueAdapter) -> None:
        self._adapters[adapter.venue] = adapter

    def get(self, venue: Venue) -> Optional[VenueAdapter]:
        return self._adapters.get(venue)

    def all(self) -> List[VenueAdapter]:
        return list(self._adapters.values())


# Global registry
adapter_registry = AdapterRegistry()