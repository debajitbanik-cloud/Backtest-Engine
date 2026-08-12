"""
Position Sizing Agent
Calculates optimal position size based on risk parameters, confluence, and account state.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List, Literal
from enum import Enum

from core.base_agent import BaseAgent, AgentConfig, AgentStatus
from core.event_bus import EventBus, Event, EventType, event_bus


class SizingMethod(Enum):
    """Position sizing methods."""
    FIXED_RISK = "fixed_risk"           # Fixed % of account per trade
    KELLY_CRITERION = "kelly"           # Kelly criterion based on win rate
    VOLATILITY_ADJUSTED = "vol_adjusted"  # ATR-based sizing
    CONFLUENCE_WEIGHTED = "confluence_weighted"  # Weighted by confluence strength
    MARTINGALE = "martingale"           # Increase after losses (dangerous)
    ANTI_MARTINGALE = "anti_martingale" # Increase after wins


@dataclass
class PositionSizeResult:
    """Position sizing calculation result."""
    symbol: str
    side: Literal["long", "short"]
    size: float  # Contract/coin quantity
    notional_value: float  # USD value
    risk_amount: float  # Max loss in USD
    risk_pct: float  # % of account
    leverage: float
    entry_price: float
    stop_loss: float
    take_profit: Optional[float]
    method: SizingMethod
    confidence: float
    reasoning: str
    timestamp: datetime


@dataclass
class SizingConfig:
    """Configuration for position sizing."""
    default_method: SizingMethod = SizingMethod.CONFLUENCE_WEIGHTED
    max_risk_per_trade: float = 0.02  # 2% of account
    max_portfolio_risk: float = 0.10  # 10% total portfolio risk
    max_leverage: float = 20.0
    min_leverage: float = 1.0
    kelly_win_rate: float = 0.55
    kelly_win_loss_ratio: float = 1.5
    atr_multiplier: float = 2.0
    atr_period: int = 14
    confluence_boost: float = 1.5  # Multiplier for strong confluence
    max_position_pct: float = 0.20  # Max 20% in single position
    correlation_limit: float = 0.7  # Max correlation between positions


class PositionSizingAgent(BaseAgent):
    """
    Calculates optimal position sizes based on multiple factors.
    
    Responsibilities:
    - Calculate position size using configured method
    - Incorporate confluence signals for sizing
    - Respect risk limits (per trade, portfolio, correlation)
    - Coordinate with LeverageAdjustmentAgent
    - Publish sizing decisions for execution
    """
    
    def __init__(self, config: AgentConfig, event_bus: EventBus = None):
        super().__init__(config, event_bus)
        
        sizing_config = config.config.get("sizing", {})
        # Convert method string to enum
        method_str = sizing_config.get("default_method", "confluence_weighted")
        sizing_config["default_method"] = SizingMethod(method_str)
        self.sizing_config = SizingConfig(**sizing_config)
        
        # State
        self._account_balance: float = 0.0
        self._available_margin: float = 0.0
        self._open_positions: Dict[str, Dict] = {}
        self._confluence_signals: Dict[str, Dict] = {}
        self._bias_signals: Dict[str, Dict] = {}
        self._leverage_settings: Dict[str, float] = {}
        self._price_data: Dict[str, float] = {}
        self._atr_values: Dict[str, float] = {}
        self._trade_history: List[Dict] = []  # For Kelly calculation
        
        # Subscribe to events
        self.config.subscriptions = [
            EventType.CONFLUENCE_SIGNAL,
            EventType.BIAS_SIGNAL,
            EventType.LEVERAGE_ADJUSTMENT,
            EventType.POSITION_OPEN,
            EventType.POSITION_CLOSE,
            EventType.POSITION_UPDATE,
            EventType.MARKET_TICK,
            EventType.AGENT_TUNING,
        ]
    
    async def initialize(self) -> None:
        """Initialize the agent."""
        self.status = AgentStatus.RUNNING
        await self._subscribe_to_events()
        
        await self._publish(EventType.AGENT_REGISTERED, {
            "agent": self.name,
            "capabilities": ["position_sizing", "risk_management", "kelly_criterion"],
            "config": {k: v.value if isinstance(v, Enum) else v for k, v in self.sizing_config.__dict__.items()}
        })
    
    async def start(self) -> None:
        """Start the agent."""
        self._running = True
        asyncio.create_task(self._sizing_loop())
        asyncio.create_task(self._run_heartbeat())
    
    async def stop(self) -> None:
        """Stop the agent."""
        self._running = False
        self.status = AgentStatus.STOPPED
    
    async def _handle_event(self, event: Event) -> None:
        """Handle incoming events."""
        self.update_heartbeat()
        
        if event.type == EventType.CONFLUENCE_SIGNAL:
            await self._on_confluence_signal(event)
        elif event.type == EventType.BIAS_SIGNAL:
            await self._on_bias_signal(event)
        elif event.type == EventType.LEVERAGE_ADJUSTMENT:
            await self._on_leverage_adjustment(event)
        elif event.type == EventType.POSITION_OPEN:
            await self._on_position_open(event)
        elif event.type == EventType.POSITION_CLOSE:
            await self._on_position_close(event)
        elif event.type == EventType.POSITION_UPDATE:
            await self._on_position_update(event)
        elif event.type == EventType.MARKET_TICK:
            await self._on_market_tick(event)
        elif event.type == EventType.AGENT_TUNING:
            await self._on_tuning(event)
    
    async def _on_confluence_signal(self, event: Event) -> None:
        """Store confluence signal for sizing."""
        payload = event.payload
        symbol = payload.get("symbol")
        if symbol:
            self._confluence_signals[symbol] = payload
    
    async def _on_bias_signal(self, event: Event) -> None:
        """Store bias signal."""
        payload = event.payload
        symbol = payload.get("symbol")
        if symbol:
            self._bias_signals[symbol] = payload
    
    async def _on_leverage_adjustment(self, event: Event) -> None:
        """Update leverage from LeverageAdjustmentAgent."""
        payload = event.payload
        symbol = payload.get("symbol")
        new_leverage = payload.get("new_leverage")
        if symbol and new_leverage:
            self._leverage_settings[symbol] = new_leverage
    
    async def _on_position_open(self, event: Event) -> None:
        """Track open positions."""
        payload = event.payload
        symbol = payload.get("symbol")
        if symbol:
            self._open_positions[symbol] = payload
    
    async def _on_position_close(self, event: Event) -> None:
        """Track closed positions for Kelly."""
        payload = event.payload
        symbol = payload.get("symbol")
        pnl = payload.get("pnl", 0)
        entry = payload.get("entry_price", 0)
        exit_price = payload.get("exit_price", 0)
        size = payload.get("size", 0)
        
        if symbol:
            # Record trade for Kelly
            self._trade_history.append({
                "symbol": symbol,
                "pnl": pnl,
                "entry": entry,
                "exit": exit_price,
                "size": size,
                "timestamp": datetime.utcnow()
            })
            # Keep last 100 trades
            if len(self._trade_history) > 100:
                self._trade_history = self._trade_history[-100:]
            
            self._open_positions.pop(symbol, None)
    
    async def _on_position_update(self, event: Event) -> None:
        """Update position tracking."""
        payload = event.payload
        symbol = payload.get("symbol")
        if symbol and symbol in self._open_positions:
            self._open_positions[symbol].update(payload)
    
    async def _on_market_tick(self, event: Event) -> None:
        """Update price data."""
        payload = event.payload
        symbol = payload.get("symbol")
        price = payload.get("price")
        if symbol and price:
            self._price_data[symbol] = price
    
    async def _on_tuning(self, event: Event) -> None:
        """Handle tuning from ManagerAgent."""
        payload = event.payload
        if payload.get("target_agent") == self.name:
            params = payload.get("parameters", {})
            for key, value in params.items():
                if key == "default_method" and isinstance(value, str):
                    value = SizingMethod(value)
                if hasattr(self.sizing_config, key):
                    setattr(self.sizing_config, key, value)
    
    async def calculate_position_size(self, symbol: str, side: str, 
                                     entry_price: float, stop_loss: float,
                                     take_profit: Optional[float] = None) -> PositionSizeResult:
        """Calculate position size for a trade."""
        # Get current account state
        account_equity = self._account_balance + sum(p.get("unrealized_pnl", 0) for p in self._open_positions.values())
        
        # Get signals
        confluence = self._confluence_signals.get(symbol, {})
        bias = self._bias_signals.get(symbol, {})
        leverage = self._leverage_settings.get(symbol, self.sizing_config.max_leverage)
        atr = self._atr_values.get(symbol, entry_price * 0.02)  # Default 2% ATR
        
        # Calculate risk per trade
        max_risk_usd = account_equity * self.sizing_config.max_risk_per_trade
        
        # Distance to stop loss
        sl_distance = abs(entry_price - stop_loss)
        if sl_distance == 0:
            sl_distance = entry_price * 0.01  # Fallback 1%
        
        # Base size from risk
        base_size = max_risk_usd / sl_distance
        
        # Apply sizing method
        method = self.sizing_config.default_method
        size = base_size
        confidence = 0.5
        reasoning = f"Base risk: ${max_risk_usd:.2f}, SL distance: ${sl_distance:.2f}"
        
        if method == SizingMethod.FIXED_RISK:
            size = base_size
            reasoning += " | Fixed risk method"
            
        elif method == SizingMethod.KELLY_CRITERION:
            kelly_fraction = self._calculate_kelly()
            size = base_size * kelly_fraction
            confidence = min(kelly_fraction * 2, 1.0)
            reasoning += f" | Kelly fraction: {kelly_fraction:.2f}"
            
        elif method == SizingMethod.VOLATILITY_ADJUSTED:
            # Adjust for volatility
            vol_adjustment = min(1.0, (entry_price * 0.02) / atr)  # Normalize to 2% baseline
            size = base_size * vol_adjustment
            reasoning += f" | Vol adjustment: {vol_adjustment:.2f}"
            
        elif method == SizingMethod.CONFLUENCE_WEIGHTED:
            confluence_result = confluence.get("result", "neutral")
            confluence_conf = confluence.get("confidence", 0.5)
            
            if confluence_result in ["strong_bullish", "strong_bearish"]:
                size = base_size * self.sizing_config.confluence_boost * confluence_conf
            elif confluence_result in ["bullish", "bearish"]:
                size = base_size * confluence_conf
            else:
                size = base_size * 0.5  # Reduce for neutral
            
            confidence = confluence_conf
            reasoning += f" | Confluence: {confluence_result} ({confluence_conf:.2f})"
        
        # Apply leverage constraint
        notional = size * entry_price
        max_notional = self._available_margin * leverage
        if notional > max_notional:
            size = max_notional / entry_price
            reasoning += " | Capped by margin"
        
        # Apply max position % constraint
        max_position_usd = account_equity * self.sizing_config.max_position_pct
        if notional > max_position_usd:
            size = max_position_usd / entry_price
            reasoning += " | Capped by max position %"
        
        # Apply portfolio risk limit
        current_portfolio_risk = sum(
            abs(p.get("size", 0) * p.get("entry_price", 0) - p.get("size", 0) * p.get("stop_loss", 0))
            for p in self._open_positions.values()
        )
        new_trade_risk = size * sl_distance
        if current_portfolio_risk + new_trade_risk > account_equity * self.sizing_config.max_portfolio_risk:
            # Scale down
            allowed_risk = account_equity * self.sizing_config.max_portfolio_risk - current_portfolio_risk
            if allowed_risk > 0:
                size = allowed_risk / sl_distance
            else:
                size = 0
            reasoning += " | Scaled for portfolio risk limit"
        
        # Correlation check (simplified)
        if self._check_correlation_limit(symbol, side):
            size *= 0.5
            reasoning += " | Reduced for correlation"
        
        # Final checks
        size = max(0, size)
        notional = size * entry_price
        risk_amount = size * sl_distance
        risk_pct = risk_amount / account_equity if account_equity > 0 else 0
        
        return PositionSizeResult(
            symbol=symbol,
            side=side,
            size=size,
            notional_value=notional,
            risk_amount=risk_amount,
            risk_pct=risk_pct,
            leverage=leverage,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            method=method,
            confidence=confidence,
            reasoning=reasoning,
            timestamp=datetime.utcnow()
        )
    
    def _calculate_kelly(self) -> float:
        """Calculate Kelly criterion fraction."""
        if len(self._trade_history) < 20:
            return 0.5  # Default conservative
        
        wins = [t for t in self._trade_history if t["pnl"] > 0]
        losses = [t for t in self._trade_history if t["pnl"] < 0]
        
        if not wins or not losses:
            return 0.5
        
        win_rate = len(wins) / len(self._trade_history)
        avg_win = np.mean([t["pnl"] for t in wins])
        avg_loss = abs(np.mean([t["pnl"] for t in losses]))
        
        if avg_loss == 0:
            return 0.5
        
        win_loss_ratio = avg_win / avg_loss
        kelly = (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio
        
        # Cap at 25% Kelly for safety
        return max(0, min(kelly * 0.25, 0.5))
    
    def _check_correlation_limit(self, symbol: str, side: str) -> bool:
        """Check if adding this position would exceed correlation limits."""
        # Simplified: check if we already have positions in same direction
        same_direction_count = sum(
            1 for p in self._open_positions.values() 
            if p.get("side") == side
        )
        return same_direction_count >= 3  # Max 3 correlated positions
    
    async def _sizing_loop(self) -> None:
        """Periodic sizing updates and ATR calculation."""
        while self._running:
            await asyncio.sleep(30)
            
            # Update ATR for symbols with positions
            for symbol in list(self._price_data.keys()):
                # Would calculate real ATR from candle data
                pass
            
            await self._publish(EventType.AGENT_HEARTBEAT, {
                "agent": self.name,
                "status": self.status.value,
                "account_equity": self._account_balance,
                "open_positions": len(self._open_positions),
                "methods": self.sizing_config.default_method.value
            })
    
    # Public method for other agents to request sizing
    async def request_sizing(self, symbol: str, side: str, entry: float, 
                            sl: float, tp: float = None) -> PositionSizeResult:
        """Public interface for sizing requests."""
        return await self.calculate_position_size(symbol, side, entry, sl, tp)