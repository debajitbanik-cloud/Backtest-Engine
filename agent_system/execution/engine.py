"""
Execution Engine — orchestrates Risk Overlay -> ExecutionIntent -> VenueAdapter.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from execution.contracts import (
    VenueAdapter,
    RiskOverlay,
    PortfolioState,
    RiskLimits,
    RiskCheckResult,
    adapter_registry,
    Venue,
)
from shared.domain import (
    Signal,
    ExecutionIntent,
    Order,
    Fill,
    Position,
    Instrument,
    OrderStatus,
    SignalType,
)


@dataclass
class ExecutionConfig:
    """Configuration for the execution engine."""
    default_venue: Venue = Venue.DELTA
    enable_reconciliation: bool = True
    reconciliation_interval_seconds: int = 30
    max_slippage_bps: int = 10
    default_time_in_force: str = "GTC"


class DefaultRiskOverlay(RiskOverlay):
    """Default risk overlay implementation using PortfolioState."""

    def __init__(self, limits: Optional[RiskLimits] = None):
        self.limits = limits or RiskLimits()

    async def evaluate_signal(self, signal: Signal, portfolio_state: PortfolioState) -> RiskCheckResult:
        checks = {}
        notes = []

        # Check portfolio drawdown
        if portfolio_state.total_equity > 0:
            current_drawdown = -portfolio_state.daily_pnl / portfolio_state.total_equity
            checks["max_drawdown"] = current_drawdown <= self.limits.max_portfolio_drawdown
            if not checks["max_drawdown"]:
                notes.append(f"Portfolio drawdown {current_drawdown:.2%} exceeds limit {self.limits.max_portfolio_drawdown:.2%}")

        # Check daily loss
        checks["daily_loss"] = abs(portfolio_state.daily_pnl) <= portfolio_state.total_equity * self.limits.max_daily_loss
        if not checks["daily_loss"]:
            notes.append(f"Daily loss {portfolio_state.daily_pnl} exceeds limit")

        # Check position size limits
        if signal.instrument:
            symbol = signal.instrument.symbol
            if symbol in portfolio_state.positions:
                pos = portfolio_state.positions[symbol]
                pos_value = pos.quantity * (pos.current_price or pos.entry_price)
                pct = pos_value / portfolio_state.total_equity if portfolio_state.total_equity > 0 else Decimal("1")
                checks["position_size"] = pct <= self.limits.max_position_size_pct
                if not checks["position_size"]:
                    notes.append(f"Position size {pct:.2%} exceeds limit {self.limits.max_position_size_pct:.2%}")

        # Check margin
        margin_ratio = portfolio_state.used_margin / portfolio_state.available_margin if portfolio_state.available_margin > 0 else Decimal("1")
        checks["margin_warning"] = margin_ratio <= self.limits.margin_warning
        checks["margin_critical"] = margin_ratio <= self.limits.margin_critical
        if not checks["margin_warning"]:
            notes.append(f"Margin ratio {margin_ratio:.2%} above warning threshold")

        passed = all(checks.values())
        return RiskCheckResult(
            passed=passed,
            checks=checks,
            notes=notes,
        )

    async def evaluate_intent(self, intent: ExecutionIntent, portfolio_state: PortfolioState) -> RiskCheckResult:
        # Re-use signal evaluation for now
        # Could add intent-specific checks (slippage, etc.)
        signal = Signal(
            id=intent.signal_id,
            strategy_id=intent.strategy_id,
            instrument=intent.instrument,
            signal_type=SignalType.ENTRY,
            side=intent.order.side,
            quantity=intent.order.quantity,
            price=intent.order.price,
        )
        return await self.evaluate_signal(signal, portfolio_state)


class ExecutionEngine:
    """
    Core execution engine that coordinates:
    1. Risk Overlay evaluation
    2. ExecutionIntent creation
    3. Venue adapter routing
    4. Order lifecycle management
    5. Reconciliation
    """

    def __init__(
        self,
        config: Optional[ExecutionConfig] = None,
        risk_overlay: Optional[RiskOverlay] = None,
    ):
        self.config = config or ExecutionConfig()
        self.risk_overlay = risk_overlay or DefaultRiskOverlay()
        self.adapter_registry = adapter_registry
        self._portfolio_state: Optional[PortfolioState] = None
        self._running = False
        self._reconciliation_task: Optional[asyncio.Task] = None

    async def initialize(self, portfolio_state: PortfolioState) -> None:
        """Initialize with portfolio state and connect adapters."""
        self._portfolio_state = portfolio_state
        # Connect all registered adapters
        for adapter in self.adapter_registry.all():
            try:
                await adapter.connect()
            except Exception as e:
                print(f"Warning: Failed to connect adapter {adapter.venue}: {e}")

    async def start(self) -> None:
        """Start background tasks."""
        self._running = True
        if self.config.enable_reconciliation:
            self._reconciliation_task = asyncio.create_task(self._reconciliation_loop())

    async def stop(self) -> None:
        """Stop background tasks and disconnect adapters."""
        self._running = False
        if self._reconciliation_task:
            self._reconciliation_task.cancel()
            try:
                await self._reconciliation_task
            except asyncio.CancelledError:
                pass
        for adapter in self.adapter_registry.all():
            try:
                await adapter.disconnect()
            except Exception:
                pass

    def update_portfolio_state(self, state: PortfolioState) -> None:
        """Update the current portfolio state."""
        self._portfolio_state = state

    async def process_signal(self, signal: Signal) -> Optional[ExecutionIntent]:
        """
        Process a signal through risk overlay and create execution intent.
        Returns the intent if approved, None if rejected.
        """
        if not self._portfolio_state:
            raise RuntimeError("Portfolio state not initialized")

        # Evaluate signal through risk overlay
        risk_result = await self.risk_overlay.evaluate_signal(signal, self._portfolio_state)

        if not risk_result.passed:
            print(f"Signal {signal.id} rejected by risk overlay: {risk_result.notes}")
            return None

        # Determine venue
        venue = signal.instrument.get_venue_symbol(self.config.default_venue)
        adapter = self.adapter_registry.get(self.config.default_venue)
        if not adapter:
            raise RuntimeError(f"No adapter for venue {self.config.default_venue}")

        # Create order from signal
        order = Order(
            strategy_id=signal.strategy_id,
            instrument=signal.instrument,
            venue=self.config.default_venue,
            side=signal.side or OrderSide.BUY,
            quantity=risk_result.adjusted_quantity or signal.quantity or Decimal("1"),
            price=risk_result.adjusted_price or signal.price,
            stop_price=risk_result.adjusted_stop or signal.stop_price,
            take_profit=risk_result.adjusted_take_profit or signal.take_profit_price,
            time_in_force=self.config.default_time_in_force,
        )

        # Create execution intent
        intent = ExecutionIntent(
            signal_id=signal.id,
            strategy_id=signal.strategy_id,
            instrument=signal.instrument,
            venue=self.config.default_venue,
            order=order,
            risk_checks_passed=risk_result.passed,
            risk_notes=risk_result.notes,
        )

        # Evaluate intent
        intent_risk = await self.risk_overlay.evaluate_intent(intent, self._portfolio_state)
        intent.risk_checks_passed = intent_risk.passed
        intent.risk_notes.extend(intent_risk.notes)

        if not intent.risk_checks_passed:
            print(f"Intent {intent.id} rejected by risk overlay: {intent.risk_notes}")
            return None

        return intent

    async def execute_intent(self, intent: ExecutionIntent) -> Order:
        """Submit an intent to the appropriate venue adapter."""
        adapter = self.adapter_registry.get(intent.venue)
        if not adapter:
            raise RuntimeError(f"No adapter for venue {intent.venue}")

        order = await adapter.submit_order(intent)
        return order

    async def cancel_order(self, venue: Venue, order_id: str) -> bool:
        """Cancel an order on a specific venue."""
        adapter = self.adapter_registry.get(venue)
        if not adapter:
            raise RuntimeError(f"No adapter for venue {venue}")
        return await adapter.cancel_order(order_id)

    async def get_positions(self) -> List[Position]:
        """Get all positions across all venues."""
        all_positions = []
        for adapter in self.adapter_registry.all():
            try:
                positions = await adapter.get_positions()
                all_positions.extend(positions)
            except Exception as e:
                print(f"Error getting positions from {adapter.venue}: {e}")
        return all_positions

    async def get_fills(self, since: Optional[datetime] = None) -> List[Fill]:
        """Get all fills across all venues."""
        all_fills = []
        for adapter in self.adapter_registry.all():
            try:
                fills = await adapter.get_fills(since)
                all_fills.extend(fills)
            except Exception as e:
                print(f"Error getting fills from {adapter.venue}: {e}")
        return all_fills

    async def reconcile_all(self) -> Dict[str, Any]:
        """Run reconciliation across all venues."""
        results = {}
        if not self._portfolio_state:
            return results

        our_positions = list(self._portfolio_state.positions.values())
        for adapter in self.adapter_registry.all():
            try:
                discrepancies = await adapter.reconcile_positions(our_positions)
                results[adapter.venue.value] = discrepancies
            except Exception as e:
                results[adapter.venue.value] = [{"type": "error", "message": str(e)}]
        return results

    async def _reconciliation_loop(self) -> None:
        """Background reconciliation task."""
        while self._running:
            try:
                await asyncio.sleep(self.config.reconciliation_interval_seconds)
                if self._running:
                    await self.reconcile_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Reconciliation error: {e}")


# Global execution engine instance
_execution_engine: Optional[ExecutionEngine] = None


def get_execution_engine(
    config: Optional[ExecutionConfig] = None,
    risk_overlay: Optional[RiskOverlay] = None,
) -> ExecutionEngine:
    global _execution_engine
    if _execution_engine is None:
        _execution_engine = ExecutionEngine(config, risk_overlay)
    return _execution_engine