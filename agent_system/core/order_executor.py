"""
Order Executor
==============
Executes real market orders via CCXT Delta with a testnet/live safety gate,
risk pre-flight, and margin-allocation-aware sizing.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, Optional

from core.event_bus import EventBus, Event, EventType, event_bus
from data.ccxt_delta_provider import ccxt_delta_provider
from data.delta_api_client import delta_client


class OrderExecutor:
    """
    Executes market orders on Delta Exchange.

    Safety rules:
    - Testnet by default. Live orders require live_unlock=True.
    - Queries RiskCheckingAgent before executing; rejects on HALT/HEDGE for symbol.
    - Amount is derived from margin_usd * leverage / current_price.
    """

    def __init__(self, event_bus: EventBus = None):
        self.event_bus = event_bus or event_bus
        self._market_map: Dict[str, str] = {}

    def _ensure_market_map(self) -> None:
        """Build a map from base symbols like SOLUSDT to CCXT market symbols."""
        if self._market_map:
            return
        try:
            markets = ccxt_delta_provider.fetch_markets()
            for market in markets.values():
                if not market.get("contract"):
                    continue
                base = market.get("base", "")
                quote = market.get("quote", "")
                if base and quote:
                    key = f"{base}{quote}"
                    self._market_map[key] = market.get("symbol")
        except Exception:
            pass

    def _normalize_symbol(self, symbol: str) -> str:
        """Map SOLUSDT -> SOL/USDT:USDT using CCXT market data."""
        self._ensure_market_map()
        if symbol in self._market_map:
            return self._market_map[symbol]
        # Fallback: try common formats
        if "/" in symbol:
            return symbol
        base = symbol.replace("USDT", "").replace("USD", "")
        for candidate in [f"{base}/USDT:USDT", f"{base}/USD:USD", f"{base}/USDT"]:
            if candidate in self._market_map.values():
                return candidate
        return f"{base}/USDT:USDT"

    def _get_current_price(self, ccxt_symbol: str) -> float:
        """Fetch last price for a CCXT symbol."""
        ticker = ccxt_delta_provider.fetch_ticker(ccxt_symbol)
        price = ticker.get("last", ticker.get("close", 0))
        return float(price) if price else 0.0

    def _risk_preflight(self, symbol: str) -> Optional[str]:
        """Check RiskCheckingAgent status for symbol. Return error string if blocked."""
        try:
            from core.agent_registry import agent_registry
            risk_agent = agent_registry.get_agent("RiskCheckingAgent")
            if not risk_agent:
                return None
            status = risk_agent.get_status()
            action = status.get("current_action") if hasattr(status, "get") else None
            if action in ("HALT", "HEDGE"):
                return f"Risk agent action={action} blocks {symbol}"
        except Exception:
            pass
        return None

    def execute_market_order(
        self,
        symbol: str,
        direction: str,
        margin_usd: float,
        leverage: float,
        live_unlock: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute a market order.

        Args:
            symbol: project symbol e.g. SOLUSDT
            direction: long | short
            margin_usd: margin allocated to this trade
            leverage: suggested leverage
            live_unlock: required for non-testnet environments

        Returns:
            dict with status, order, error, margin, leverage, amount
        """
        if direction not in ("long", "short"):
            return {"status": "rejected", "error": f"invalid direction {direction}"}
        if margin_usd <= 0 or leverage <= 0:
            return {"status": "rejected", "error": "margin and leverage must be positive"}

        # Environment / live gate
        env = getattr(delta_client.credentials, "environment", "testnet")
        if env != "testnet" and not live_unlock:
            return {
                "status": "rejected",
                "error": f"live trading disabled for {env}; set live_unlock=true",
            }

        if not ccxt_delta_provider.is_authenticated():
            return {"status": "rejected", "error": "CCXT Delta not authenticated"}

        # Risk pre-flight
        risk_error = self._risk_preflight(symbol)
        if risk_error:
            self._emit_trade_rejected(symbol, direction, risk_error)
            return {"status": "rejected", "error": risk_error}

        ccxt_symbol = self._normalize_symbol(symbol)
        price = self._get_current_price(ccxt_symbol)
        if price <= 0:
            return {"status": "rejected", "error": f"could not fetch price for {ccxt_symbol}"}

        # Amount = margin * leverage / price
        amount = (margin_usd * leverage) / price
        if amount <= 0:
            return {"status": "rejected", "error": "computed amount is zero"}

        side = "buy" if direction == "long" else "sell"
        try:
            order = ccxt_delta_provider.create_market_buy_order(
                ccxt_symbol, amount
            ) if direction == "long" else ccxt_delta_provider.create_market_sell_order(
                ccxt_symbol, amount
            )
            result = {
                "status": "executed",
                "symbol": symbol,
                "ccxt_symbol": ccxt_symbol,
                "direction": direction,
                "side": side,
                "margin_usd": margin_usd,
                "leverage": leverage,
                "amount": amount,
                "price": price,
                "order": order,
                "timestamp": datetime.utcnow().isoformat(),
            }
            self._emit_trade_executed(result)
            return result
        except Exception as e:
            error = str(e)
            self._emit_trade_rejected(symbol, direction, error)
            return {"status": "rejected", "symbol": symbol, "direction": direction, "error": error}

    def _emit_trade_executed(self, result: Dict[str, Any]) -> None:
        try:
            self.event_bus.publish(Event(
                type=EventType.TRADE_EXECUTED,
                payload=result,
                source_agent="OrderExecutor",
            ))
            self.event_bus.publish(Event(
                type=EventType.TRADE_LOG,
                payload={"message": f"Executed {result['direction']} {result['symbol']} amount={result['amount']:.6f}"},
                source_agent="OrderExecutor",
            ))
        except Exception:
            pass

    def _emit_trade_rejected(self, symbol: str, direction: str, error: str) -> None:
        try:
            self.event_bus.publish(Event(
                type=EventType.TRADE_REJECTED,
                payload={"symbol": symbol, "direction": direction, "error": error},
                source_agent="OrderExecutor",
            ))
            self.event_bus.publish(Event(
                type=EventType.TRADE_LOG,
                payload={"message": f"Rejected {direction} {symbol}: {error}"},
                source_agent="OrderExecutor",
            ))
        except Exception:
            pass


# Global executor
order_executor = OrderExecutor()
