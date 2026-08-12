"""
Strategy Execution Engine
=========================
Deploys the optimized strategy into the running agent system.
When live, executes trades via CCXT Delta in alignment with
TimeframeRecommendationAgent signals and margin allocations.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.margin_allocation_engine import margin_engine
from core.order_executor import order_executor
from data.ccxt_delta_provider import ccxt_delta_provider
from data.delta_api_client import delta_client


@dataclass
class ExecutionState:
    deployed: bool = False
    live: bool = False
    live_unlock: bool = False
    last_execution: Optional[datetime] = None
    active_symbols: List[str] = field(default_factory=list)
    last_error: Optional[str] = None
    executed_orders: List[Dict] = field(default_factory=list)


class StrategyExecutionEngine:
    """
    Manages deployment and live execution of optimized strategies.
    """

    def __init__(self):
        self.state = ExecutionState()
        self._execution_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def deploy(self, strategy: Dict[str, Any], live_unlock: bool = False) -> Dict:
        """Deploy the optimized strategy."""
        async with self._lock:
            if self.state.deployed:
                return {"status": "already_deployed"}

            self.state.deployed = True
            self.state.live = True
            self.state.live_unlock = live_unlock
            self.state.last_error = None
            self.state.active_symbols = [strategy.get("symbol", "")]
            self.state.last_execution = datetime.utcnow()

            if self._execution_task is None or self._execution_task.done():
                self._execution_task = asyncio.create_task(self._execution_loop())

            return {
                "status": "deployed",
                "live_unlock": live_unlock,
                "deployed_at": self.state.last_execution.isoformat(),
            }

    async def stop(self) -> Dict:
        """Stop live execution."""
        async with self._lock:
            self.state.live = False
            self.state.deployed = False
            self.state.live_unlock = False
            if self._execution_task and not self._execution_task.done():
                self._execution_task.cancel()
            return {"status": "stopped"}

    async def status(self) -> Dict:
        """Get execution engine status."""
        return {
            "deployed": self.state.deployed,
            "live": self.state.live,
            "live_unlock": self.state.live_unlock,
            "active_symbols": self.state.active_symbols,
            "last_execution": self.state.last_execution.isoformat() if self.state.last_execution else None,
            "last_error": self.state.last_error,
            "executed_orders": self.state.executed_orders[-20:],
        }

    async def _execution_loop(self) -> None:
        """Periodically check recommendations and execute aligned trades."""
        while self.state.live:
            try:
                await self._execute_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.state.last_error = str(e)

            await asyncio.sleep(30)

    async def _execute_once(self) -> None:
        """Execute one round of recommendation-aligned trades."""
        if not ccxt_delta_provider.is_authenticated():
            self.state.last_error = "CCXT Delta not authenticated"
            return

        # Get recommendations from the agent registry
        try:
            from core.agent_registry import agent_registry
            rec_agent = agent_registry.get_agent("TimeframeRecommendationAgent")
            if not rec_agent:
                self.state.last_error = "Recommendation agent not running"
                return

            recommendations = rec_agent.get_all_recommendations()
        except Exception as e:
            self.state.last_error = f"Failed to get recommendations: {e}"
            return

        # Get account equity for margin allocation
        try:
            balance = await delta_client.get_balance()
            account_equity = balance.get("net_equity", 0)
            available_margin = balance.get("available_balance", 0)
        except Exception:
            account_equity = 0
            available_margin = 0

        # Get current positions to avoid duplicate direction
        try:
            existing_positions = await delta_client.get_positions()
        except Exception:
            existing_positions = []

        position_by_symbol = {}
        for p in existing_positions:
            pos_symbol = p.get("symbol", "")
            position_by_symbol[pos_symbol] = p

        # For each active symbol, check if we should execute
        for symbol in self.state.active_symbols:
            rec = recommendations.get(symbol)
            if not rec:
                continue

            direction = rec.get("direction")
            confidence = rec.get("confidence", 0)
            timeframe = rec.get("timeframe", "15m")
            if direction not in ("long", "short") or confidence < 0.55:
                continue

            # Check existing position direction
            existing = position_by_symbol.get(symbol)
            if existing:
                existing_dir = "long" if existing.get("size", 0) > 0 else "short"
                if existing_dir == direction:
                    continue

            # Compute margin allocation
            try:
                allocation = margin_engine.analyze_recommendation(
                    symbol=symbol,
                    direction=direction,
                    confidence=confidence,
                    account_equity=account_equity,
                    available_margin=available_margin,
                    timeframe=timeframe,
                )
            except Exception as e:
                self.state.last_error = f"Margin allocation failed for {symbol}: {e}"
                continue

            margin_usd = min(allocation.recommended_margin_usd, available_margin * 0.95)
            leverage = allocation.leverage

            # Execute via order executor
            result = order_executor.execute_market_order(
                symbol=symbol,
                direction=direction,
                margin_usd=margin_usd,
                leverage=leverage,
                live_unlock=self.state.live_unlock,
            )

            self.state.executed_orders.append(result)
            self.state.last_execution = datetime.utcnow()
            self.state.last_error = result.get("error")


# Global execution engine
execution_engine = StrategyExecutionEngine()
