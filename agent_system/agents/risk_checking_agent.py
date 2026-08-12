"""
Risk Checking Agent
Monitors positions and portfolio for risk, triggers mitigation actions.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Literal
from enum import Enum
from collections import deque

from core.base_agent import BaseAgent, AgentConfig, AgentStatus
from core.event_bus import EventBus, Event, EventType, event_bus


class RiskLevel(Enum):
    """Risk severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskAction(Enum):
    """Risk mitigation actions."""
    NONE = "none"
    REDUCE_POSITION = "reduce_position"
    CLOSE_POSITION = "close_position"
    CLOSE_ALL = "close_all"
    REDUCE_LEVERAGE = "reduce_leverage"
    HEDGE = "hedge"
    ALERT_ONLY = "alert_only"


@dataclass
class RiskAlert:
    """Risk alert with recommended action."""
    symbol: str
    risk_level: RiskLevel
    action: RiskAction
    metric: str
    current_value: float
    threshold: float
    reasoning: str
    timestamp: datetime
    position_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskConfig:
    """Risk management configuration."""
    # Portfolio limits
    max_portfolio_drawdown: float = 0.10      # 10% max drawdown
    max_daily_loss: float = 0.03              # 3% max daily loss
    max_position_size_pct: float = 0.20       # 20% max per position
    max_sector_exposure: float = 0.40         # 40% max sector (correlated)
    max_leverage: float = 20.0
    
    # Position limits
    max_hold_time_losing_hours: int = 24      # Max hold losing position
    max_consecutive_losses: int = 5           # Max consecutive losses
    loss_streak_reduction: float = 0.5        # Reduce size after streak
    
    # Margin limits
    margin_warning: float = 0.70              # 70% margin used
    margin_critical: float = 0.85             # 85% margin used
    margin_liquidation: float = 0.95          # 95% margin used
    
    # Volatility limits
    max_portfolio_volatility: float = 0.05    # 5% daily vol
    var_confidence: float = 0.95              # VaR confidence
    var_horizon_days: int = 1
    
    # Correlation
    max_correlation: float = 0.7              # Max position correlation
    
    # Mitigation
    auto_mitigate: bool = True                # Auto-execute mitigation
    mitigation_cooldown_minutes: int = 15     # Cooldown between actions


class RiskCheckingAgent(BaseAgent):
    """
    Monitors portfolio risk and triggers mitigation actions.
    
    Responsibilities:
    - Track portfolio drawdown, daily P&L
    - Monitor position concentrations
    - Detect losing streaks and held losers
    - Check margin health
    - Trigger mitigation (reduce/close positions, reduce leverage)
    - Coordinate with LeverageAdjustmentAgent and PositionSizingAgent
    """
    
    def __init__(self, config: AgentConfig, event_bus: EventBus = None):
        super().__init__(config, event_bus)
        
        risk_config = config.config.get("risk", {})
        self.risk_config = RiskConfig(**risk_config)
        
        # State
        self._account_equity: float = 0.0
        self._peak_equity: float = 0.0
        self._daily_start_equity: float = 0.0
        self._daily_pnl: float = 0.0
        self._open_positions: Dict[str, Dict] = {}
        self._closed_trades_today: List[Dict] = []
        self._consecutive_losses: int = 0
        self._last_mitigation: Optional[datetime] = None
        self._active_alerts: Dict[str, RiskAlert] = {}
        self._margin_data: Dict[str, Dict] = {}
        self._portfolio_returns: deque = deque(maxlen=288)  # 24h of 5m returns
        
        # Subscribe to events
        self.config.subscriptions = [
            EventType.POSITION_OPEN,
            EventType.POSITION_CLOSE,
            EventType.POSITION_UPDATE,
            EventType.MARKET_TICK,
            EventType.LEVERAGE_ADJUSTMENT,
            EventType.MARGIN_CALL,
            EventType.AGENT_TUNING,
        ]
    
    async def initialize(self) -> None:
        """Initialize the agent."""
        self.status = AgentStatus.RUNNING
        await self._subscribe_to_events()
        
        await self._publish(EventType.AGENT_REGISTERED, {
            "agent": self.name,
            "capabilities": ["risk_monitoring", "drawdown_control", "position_management", "auto_mitigation"],
            "config": self.risk_config.__dict__
        })
    
    async def start(self) -> None:
        """Start the agent."""
        self._running = True
        asyncio.create_task(self._risk_monitoring_loop())
        asyncio.create_task(self._run_heartbeat())
    
    async def stop(self) -> None:
        """Stop the agent."""
        self._running = False
        self.status = AgentStatus.STOPPED
    
    async def _handle_event(self, event: Event) -> None:
        """Handle incoming events."""
        self.update_heartbeat()
        
        if event.type == EventType.POSITION_OPEN:
            await self._on_position_open(event)
        elif event.type == EventType.POSITION_CLOSE:
            await self._on_position_close(event)
        elif event.type == EventType.POSITION_UPDATE:
            await self._on_position_update(event)
        elif event.type == EventType.MARKET_TICK:
            await self._on_market_tick(event)
        elif event.type == EventType.LEVERAGE_ADJUSTMENT:
            await self._on_leverage_adjustment(event)
        elif event.type == EventType.MARGIN_CALL:
            await self._on_margin_call(event)
        elif event.type == EventType.AGENT_TUNING:
            await self._on_tuning(event)
    
    async def _on_position_open(self, event: Event) -> None:
        """Track new position."""
        payload = event.payload
        symbol = payload.get("symbol")
        if symbol:
            self._open_positions[symbol] = payload
            # Initialize daily tracking if first position
            if self._daily_start_equity == 0:
                self._daily_start_equity = self._account_equity
    
    async def _on_position_close(self, event: Event) -> None:
        """Track closed position."""
        payload = event.payload
        symbol = payload.get("symbol")
        pnl = payload.get("pnl", 0)
        
        if symbol:
            self._open_positions.pop(symbol, None)
            self._closed_trades_today.append({
                "symbol": symbol,
                "pnl": pnl,
                "timestamp": datetime.utcnow()
            })
            
            # Track consecutive losses
            if pnl < 0:
                self._consecutive_losses += 1
            else:
                self._consecutive_losses = 0
    
    async def _on_position_update(self, event: Event) -> None:
        """Update position tracking."""
        payload = event.payload
        symbol = payload.get("symbol")
        if symbol and symbol in self._open_positions:
            self._open_positions[symbol].update(payload)
    
    async def _on_market_tick(self, event: Event) -> None:
        """Update equity and returns."""
        payload = event.payload
        # Would update unrealized P&L from positions
        pass
    
    async def _on_leverage_adjustment(self, event: Event) -> None:
        """Track leverage changes."""
        payload = event.payload
        symbol = payload.get("symbol")
        new_leverage = payload.get("new_leverage")
        if symbol:
            if symbol in self._open_positions:
                self._open_positions[symbol]["leverage"] = new_leverage
    
    async def _on_margin_call(self, event: Event) -> None:
        """Emergency margin call handling."""
        payload = event.payload
        symbol = payload.get("symbol")
        
        if self.risk_config.auto_mitigate:
            await self._trigger_mitigation(RiskAlert(
                symbol=symbol or "PORTFOLIO",
                risk_level=RiskLevel.CRITICAL,
                action=RiskAction.CLOSE_POSITION if symbol else RiskAction.CLOSE_ALL,
                metric="margin_call",
                current_value=1.0,
                threshold=self.risk_config.margin_liquidation,
                reasoning="Margin call received from exchange",
                timestamp=datetime.utcnow()
            ))
    
    async def _on_tuning(self, event: Event) -> None:
        """Handle tuning from ManagerAgent."""
        payload = event.payload
        if payload.get("target_agent") == self.name:
            params = payload.get("parameters", {})
            for key, value in params.items():
                if hasattr(self.risk_config, key):
                    setattr(self.risk_config, key, value)
    
    async def _risk_monitoring_loop(self) -> None:
        """Main risk monitoring loop."""
        while self._running:
            await asyncio.sleep(5)  # Check every 5 seconds
            
            await self._check_portfolio_drawdown()
            await self._check_daily_loss()
            await self._check_position_concentration()
            await self._check_losing_streak()
            await self._check_held_losers()
            await self._check_margin_health()
            await self._check_correlation()
            await self._check_volatility()
            
            # Process any triggered alerts
            await self._process_alerts()
            
            await self._publish(EventType.AGENT_HEARTBEAT, {
                "agent": self.name,
                "status": self.status.value,
                "drawdown": self._calculate_drawdown(),
                "daily_pnl_pct": self._daily_pnl / self._daily_start_equity if self._daily_start_equity > 0 else 0,
                "consecutive_losses": self._consecutive_losses,
                "open_positions": len(self._open_positions),
                "active_alerts": len(self._active_alerts)
            })
    
    def _calculate_drawdown(self) -> float:
        """Calculate current drawdown from peak."""
        if self._peak_equity == 0:
            return 0.0
        return (self._peak_equity - self._account_equity) / self._peak_equity
    
    async def _check_portfolio_drawdown(self) -> None:
        """Check portfolio drawdown limit."""
        drawdown = self._calculate_drawdown()
        
        if drawdown >= self.risk_config.max_portfolio_drawdown:
            await self._create_alert(RiskAlert(
                symbol="PORTFOLIO",
                risk_level=RiskLevel.CRITICAL,
                action=RiskAction.CLOSE_ALL,
                metric="portfolio_drawdown",
                current_value=drawdown,
                threshold=self.risk_config.max_portfolio_drawdown,
                reasoning=f"Portfolio drawdown {drawdown:.1%} exceeds limit {self.risk_config.max_portfolio_drawdown:.1%}",
                timestamp=datetime.utcnow()
            ))
        elif drawdown >= self.risk_config.max_portfolio_drawdown * 0.7:
            await self._create_alert(RiskAlert(
                symbol="PORTFOLIO",
                risk_level=RiskLevel.HIGH,
                action=RiskAction.REDUCE_POSITION,
                metric="portfolio_drawdown",
                current_value=drawdown,
                threshold=self.risk_config.max_portfolio_drawdown,
                reasoning=f"Portfolio drawdown {drawdown:.1%} approaching limit",
                timestamp=datetime.utcnow()
            ))
    
    async def _check_daily_loss(self) -> None:
        """Check daily loss limit."""
        if self._daily_start_equity == 0:
            return
        
        daily_loss_pct = -self._daily_pnl / self._daily_start_equity if self._daily_pnl < 0 else 0
        
        if daily_loss_pct >= self.risk_config.max_daily_loss:
            await self._create_alert(RiskAlert(
                symbol="PORTFOLIO",
                risk_level=RiskLevel.CRITICAL,
                action=RiskAction.CLOSE_ALL,
                metric="daily_loss",
                current_value=daily_loss_pct,
                threshold=self.risk_config.max_daily_loss,
                reasoning=f"Daily loss {daily_loss_pct:.1%} exceeds limit {self.risk_config.max_daily_loss:.1%}",
                timestamp=datetime.utcnow()
            ))
        elif daily_loss_pct >= self.risk_config.max_daily_loss * 0.7:
            await self._create_alert(RiskAlert(
                symbol="PORTFOLIO",
                risk_level=RiskLevel.HIGH,
                action=RiskAction.REDUCE_POSITION,
                metric="daily_loss",
                current_value=daily_loss_pct,
                threshold=self.risk_config.max_daily_loss,
                reasoning=f"Daily loss {daily_loss_pct:.1%} approaching limit",
                timestamp=datetime.utcnow()
            ))
    
    async def _check_position_concentration(self) -> None:
        """Check individual position size limits."""
        total_equity = self._account_equity
        if total_equity == 0:
            return
        
        for symbol, position in self._open_positions.items():
            notional = abs(position.get("size", 0) * position.get("entry_price", 0))
            pct = notional / total_equity
            
            if pct >= self.risk_config.max_position_size_pct:
                await self._create_alert(RiskAlert(
                    symbol=symbol,
                    risk_level=RiskLevel.HIGH,
                    action=RiskAction.REDUCE_POSITION,
                    metric="position_concentration",
                    current_value=pct,
                    threshold=self.risk_config.max_position_size_pct,
                    reasoning=f"Position {symbol} is {pct:.1%} of portfolio, exceeds {self.risk_config.max_position_size_pct:.1%}",
                    timestamp=datetime.utcnow(),
                    position_data=position
                ))
    
    async def _check_losing_streak(self) -> None:
        """Check consecutive losses."""
        if self._consecutive_losses >= self.risk_config.max_consecutive_losses:
            await self._create_alert(RiskAlert(
                symbol="PORTFOLIO",
                risk_level=RiskLevel.HIGH,
                action=RiskAction.REDUCE_POSITION,
                metric="consecutive_losses",
                current_value=self._consecutive_losses,
                threshold=self.risk_config.max_consecutive_losses,
                reasoning=f"{self._consecutive_losses} consecutive losses, reducing position sizes",
                timestamp=datetime.utcnow()
            ))
    
    async def _check_held_losers(self) -> None:
        """Check for losing positions held too long."""
        now = datetime.utcnow()
        
        for symbol, position in self._open_positions.items():
            unrealized_pnl = position.get("unrealized_pnl", 0)
            entry_time = position.get("entry_time")
            
            if unrealized_pnl < 0 and entry_time:
                if isinstance(entry_time, str):
                    entry_time = datetime.fromisoformat(entry_time)
                
                hold_hours = (now - entry_time).total_seconds() / 3600
                
                if hold_hours >= self.risk_config.max_hold_time_losing_hours:
                    await self._create_alert(RiskAlert(
                        symbol=symbol,
                        risk_level=RiskLevel.MEDIUM,
                        action=RiskAction.CLOSE_POSITION,
                        metric="held_loser",
                        current_value=hold_hours,
                        threshold=self.risk_config.max_hold_time_losing_hours,
                        reasoning=f"Losing position {symbol} held for {hold_hours:.1f}h, unrealized P&L: {unrealized_pnl:.2f}",
                        timestamp=now,
                        position_data=position
                    ))
    
    async def _check_margin_health(self) -> None:
        """Check margin levels across positions."""
        for symbol, margin in self._margin_data.items():
            margin_ratio = margin.get("margin_ratio", 0)
            
            if margin_ratio >= self.risk_config.margin_liquidation:
                await self._create_alert(RiskAlert(
                    symbol=symbol,
                    risk_level=RiskLevel.CRITICAL,
                    action=RiskAction.CLOSE_POSITION,
                    metric="margin_ratio",
                    current_value=margin_ratio,
                    threshold=self.risk_config.margin_liquidation,
                    reasoning=f"Margin ratio {margin_ratio:.1%} near liquidation",
                    timestamp=datetime.utcnow()
                ))
            elif margin_ratio >= self.risk_config.margin_critical:
                await self._create_alert(RiskAlert(
                    symbol=symbol,
                    risk_level=RiskLevel.HIGH,
                    action=RiskAction.REDUCE_LEVERAGE,
                    metric="margin_ratio",
                    current_value=margin_ratio,
                    threshold=self.risk_config.margin_critical,
                    reasoning=f"Margin ratio {margin_ratio:.1%} critical",
                    timestamp=datetime.utcnow()
                ))
            elif margin_ratio >= self.risk_config.margin_warning:
                await self._create_alert(RiskAlert(
                    symbol=symbol,
                    risk_level=RiskLevel.MEDIUM,
                    action=RiskAction.ALERT_ONLY,
                    metric="margin_ratio",
                    current_value=margin_ratio,
                    threshold=self.risk_config.margin_warning,
                    reasoning=f"Margin ratio {margin_ratio:.1%} elevated",
                    timestamp=datetime.utcnow()
                ))
    
    async def _check_correlation(self) -> None:
        """Check position correlations (simplified)."""
        # In production, would calculate actual correlation matrix
        # For now, check if too many positions in same direction
        long_count = sum(1 for p in self._open_positions.values() if p.get("side") == "long")
        short_count = sum(1 for p in self._open_positions.values() if p.get("side") == "short")
        total = len(self._open_positions)
        
        if total > 0:
            max_side_pct = max(long_count, short_count) / total
            if max_side_pct > self.risk_config.max_correlation:
                await self._create_alert(RiskAlert(
                    symbol="PORTFOLIO",
                    risk_level=RiskLevel.MEDIUM,
                    action=RiskAction.REDUCE_POSITION,
                    metric="directional_concentration",
                    current_value=max_side_pct,
                    threshold=self.risk_config.max_correlation,
                    reasoning=f"{max_side_pct:.0%} positions in same direction",
                    timestamp=datetime.utcnow()
                ))
    
    async def _check_volatility(self) -> None:
        """Check portfolio volatility."""
        if len(self._portfolio_returns) < 20:
            return
        
        daily_vol = np.std(list(self._portfolio_returns)) * np.sqrt(288)
        
        if daily_vol >= self.risk_config.max_portfolio_volatility:
            await self._create_alert(RiskAlert(
                symbol="PORTFOLIO",
                risk_level=RiskLevel.HIGH,
                action=RiskAction.REDUCE_POSITION,
                metric="portfolio_volatility",
                current_value=daily_vol,
                threshold=self.risk_config.max_portfolio_volatility,
                reasoning=f"Portfolio volatility {daily_vol:.1%} exceeds limit",
                timestamp=datetime.utcnow()
            ))
    
    async def _create_alert(self, alert: RiskAlert) -> None:
        """Create or update a risk alert."""
        key = f"{alert.symbol}_{alert.metric}"
        
        # Check if similar alert exists and is recent
        if key in self._active_alerts:
            existing = self._active_alerts[key]
            if (datetime.utcnow() - existing.timestamp).total_seconds() < 60:
                return  # Don't spam alerts
        
        self._active_alerts[key] = alert
        
        # Publish risk alert event
        await self._publish(EventType.RISK_ALERT, {
            "symbol": alert.symbol,
            "risk_level": alert.risk_level.value,
            "action": alert.action.value,
            "metric": alert.metric,
            "current_value": alert.current_value,
            "threshold": alert.threshold,
            "reasoning": alert.reasoning
        })
    
    async def _process_alerts(self) -> None:
        """Process active alerts and trigger mitigation."""
        if not self.risk_config.auto_mitigate:
            return
        
        # Check cooldown
        if self._last_mitigation and (datetime.utcnow() - self._last_mitigation).total_seconds() < self.risk_config.mitigation_cooldown_minutes * 60:
            return
        
        # Find highest priority alert
        critical_alerts = [a for a in self._active_alerts.values() if a.risk_level == RiskLevel.CRITICAL]
        high_alerts = [a for a in self._active_alerts.values() if a.risk_level == RiskLevel.HIGH]
        
        alert_to_act = None
        if critical_alerts:
            alert_to_act = max(critical_alerts, key=lambda a: a.current_value)
        elif high_alerts:
            alert_to_act = max(high_alerts, key=lambda a: a.current_value)
        
        if alert_to_act:
            await self._trigger_mitigation(alert_to_act)
    
    async def _trigger_mitigation(self, alert: RiskAlert) -> None:
        """Execute risk mitigation action."""
        self._last_mitigation = datetime.utcnow()
        
        action = alert.action
        symbol = alert.symbol
        
        mitigation_payload = {
            "symbol": symbol,
            "action": action.value,
            "triggered_by": alert.metric,
            "reasoning": alert.reasoning,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if action == RiskAction.CLOSE_ALL:
            mitigation_payload["symbols"] = list(self._open_positions.keys())
            await self._publish(EventType.RISK_MITIGATION, mitigation_payload)
            
        elif action == RiskAction.CLOSE_POSITION and symbol in self._open_positions:
            mitigation_payload["position"] = self._open_positions[symbol]
            await self._publish(EventType.RISK_MITIGATION, mitigation_payload)
            
        elif action == RiskAction.REDUCE_POSITION:
            if symbol != "PORTFOLIO" and symbol in self._open_positions:
                mitigation_payload["position"] = self._open_positions[symbol]
                mitigation_payload["reduce_pct"] = 0.5
            else:
                # Reduce all positions
                mitigation_payload["symbols"] = list(self._open_positions.keys())
                mitigation_payload["reduce_pct"] = 0.3
            await self._publish(EventType.RISK_MITIGATION, mitigation_payload)
            
        elif action == RiskAction.REDUCE_LEVERAGE:
            await self._publish(EventType.RISK_MITIGATION, {
                **mitigation_payload,
                "leverage_reduction": 0.5
            })
        
        elif action == RiskAction.HEDGE:
            # Request protective option overlay from OptionsAgent
            await self._publish(EventType.RISK_ALERT, {
                "symbol": symbol,
                "action": "HEDGE",
                "triggered_by": alert.metric,
                "reasoning": alert.reasoning,
                "timestamp": datetime.utcnow().isoformat()
            })
            await self._publish(EventType.RISK_MITIGATION, {
                **mitigation_payload,
                "hedge_request": True,
                "hedge_size": alert.position_data.get("size", 0) if alert.position_data else 0,
            })
        
        # Clear alert after action
        key = f"{alert.symbol}_{alert.metric}"
        self._active_alerts.pop(key, None)
        
        # Update metrics
        self._metrics["last_mitigation"] = action.value
        self._metrics["mitigation_count"] = self._metrics.get("mitigation_count", 0) + 1


import numpy as np