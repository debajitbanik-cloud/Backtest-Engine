"""
Trade Master Agent
Logs every trade, analyzes performance, optimizes strategy, sends daily reports.
"""
from __future__ import annotations
import asyncio
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Literal
from collections import deque
from pathlib import Path
import numpy as np

from core.base_agent import BaseAgent, AgentConfig, AgentStatus
from core.event_bus import EventBus, Event, EventType, event_bus


@dataclass
class TradeRecord:
    """Complete trade record."""
    trade_id: str
    symbol: str
    side: Literal["long", "short"]
    entry_price: float
    exit_price: Optional[float]
    size: float
    notional: float
    leverage: float
    entry_time: datetime
    exit_time: Optional[datetime]
    hold_duration_minutes: Optional[float]
    pnl: float
    pnl_pct: float
    fees: float
    mode: str  # scalping/swing
    confluence_result: str
    bias_direction: str
    bias_confidence: float
    stop_loss: float
    take_profit: Optional[float]
    exit_reason: str  # tp/sl/manual/risk_mitigation
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DailyReport:
    """Daily performance report."""
    date: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    total_pnl_pct: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_drawdown: float
    sharpe_ratio: float
    scalping_trades: int
    swing_trades: int
    scalping_pnl: float
    swing_pnl: float
    best_trade: Dict[str, Any]
    worst_trade: Dict[str, Any]
    mode_performance: Dict[str, Dict]
    symbol_performance: Dict[str, Dict]
    optimization_suggestions: List[str]


@dataclass
class OptimizationResult:
    """Strategy optimization result."""
    parameter: str
    old_value: Any
    new_value: Any
    expected_improvement: float
    confidence: float
    reasoning: str


class TradeMasterAgent(BaseAgent):
    """
    Logs trades, analyzes performance, optimizes strategy, sends daily reports.
    
    Responsibilities:
    - Record every trade with full context
    - Calculate performance metrics (Sharpe, profit factor, etc.)
    - Analyze performance by mode, symbol, timeframe
    - Run optimization to tune agent parameters
    - Generate daily reports for ManagerAgent
    - Persist trade history to disk
    """
    
    def __init__(self, config: AgentConfig, event_bus: EventBus = None):
        super().__init__(config, event_bus)
        
        master_config = config.config.get("trade_master", {})
        self.data_dir = Path(master_config.get("data_dir", "data/trades"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir = Path(master_config.get("report_dir", "reports"))
        self.report_dir.mkdir(parents=True, exist_ok=True)
        
        self.optimization_enabled = master_config.get("optimization_enabled", True)
        self.optimization_interval_hours = master_config.get("optimization_interval_hours", 24)
        self.min_trades_for_optimization = master_config.get("min_trades_for_optimization", 50)
        
        # State
        self._trades: List[TradeRecord] = []
        self._open_trades: Dict[str, Dict] = {}  # trade_id -> partial trade data
        self._daily_stats: Dict[str, Dict] = {}
        self._last_optimization: Optional[datetime] = None
        self._optimization_results: List[OptimizationResult] = []
        self._parameter_bounds: Dict[str, tuple] = {}  # For optimization
        
        # Subscribe to events
        self.config.subscriptions = [
            EventType.POSITION_OPEN,
            EventType.POSITION_CLOSE,
            EventType.TRADE_EXECUTED,
            EventType.TRADE_REJECTED,
            EventType.MODE_SWITCH,
            EventType.AGENT_TUNING,
        ]
    
    async def initialize(self) -> None:
        """Initialize the agent."""
        self.status = AgentStatus.RUNNING
        await self._subscribe_to_events()
        
        # Load existing trades
        await self._load_trades()
        
        await self._publish(EventType.AGENT_REGISTERED, {
            "agent": self.name,
            "capabilities": ["trade_logging", "performance_analysis", "optimization", "daily_reporting"],
            "total_trades_logged": len(self._trades)
        })
    
    async def start(self) -> None:
        """Start the agent."""
        self._running = True
        asyncio.create_task(self._daily_report_loop())
        asyncio.create_task(self._optimization_loop())
        asyncio.create_task(self._run_heartbeat())
    
    async def stop(self) -> None:
        """Stop the agent."""
        self._running = False
        self.status = AgentStatus.STOPPED
        await self._save_trades()
    
    async def _handle_event(self, event: Event) -> None:
        """Handle incoming events."""
        self.update_heartbeat()
        
        if event.type == EventType.POSITION_OPEN:
            await self._on_position_open(event)
        elif event.type == EventType.POSITION_CLOSE:
            await self._on_position_close(event)
        elif event.type == EventType.TRADE_EXECUTED:
            await self._on_trade_executed(event)
        elif event.type == EventType.TRADE_REJECTED:
            await self._on_trade_rejected(event)
        elif event.type == EventType.MODE_SWITCH:
            await self._on_mode_switch(event)
        elif event.type == EventType.AGENT_TUNING:
            await self._on_tuning(event)
    
    async def _on_position_open(self, event: Event) -> None:
        """Record trade entry."""
        payload = event.payload
        trade_id = payload.get("trade_id", f"trade_{datetime.utcnow().timestamp()}")
        
        self._open_trades[trade_id] = {
            "trade_id": trade_id,
            "symbol": payload.get("symbol"),
            "side": payload.get("side"),
            "entry_price": payload.get("entry_price"),
            "size": payload.get("size"),
            "notional": payload.get("notional"),
            "leverage": payload.get("leverage"),
            "entry_time": datetime.utcnow(),
            "stop_loss": payload.get("stop_loss"),
            "take_profit": payload.get("take_profit"),
            "mode": payload.get("mode", "unknown"),
            "confluence_result": payload.get("confluence_result", "neutral"),
            "bias_direction": payload.get("bias_direction", "neutral"),
            "bias_confidence": payload.get("bias_confidence", 0.5),
            "fees": payload.get("fees", 0),
            "metadata": payload.get("metadata", {})
        }
    
    async def _on_position_close(self, event: Event) -> None:
        """Record trade exit and complete trade record."""
        payload = event.payload
        trade_id = payload.get("trade_id")
        
        if not trade_id or trade_id not in self._open_trades:
            # Try to find by symbol
            symbol = payload.get("symbol")
            for tid, tdata in self._open_trades.items():
                if tdata["symbol"] == symbol:
                    trade_id = tid
                    break
        
        if not trade_id or trade_id not in self._open_trades:
            return
        
        trade_data = self._open_trades.pop(trade_id)
        exit_time = datetime.utcnow()
        exit_price = payload.get("exit_price")
        pnl = payload.get("pnl", 0)
        exit_reason = payload.get("exit_reason", "manual")
        
        # Calculate metrics
        hold_duration = (exit_time - trade_data["entry_time"]).total_seconds() / 60
        entry_price = trade_data["entry_price"]
        size = trade_data["size"]
        notional = trade_data["notional"]
        side = trade_data["side"]
        
        if side == "long":
            pnl_pct = (exit_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - exit_price) / entry_price
        
        # Create complete trade record
        trade = TradeRecord(
            trade_id=trade_id,
            symbol=trade_data["symbol"],
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            size=size,
            notional=notional,
            leverage=trade_data["leverage"],
            entry_time=trade_data["entry_time"],
            exit_time=exit_time,
            hold_duration_minutes=hold_duration,
            pnl=pnl,
            pnl_pct=pnl_pct,
            fees=trade_data["fees"],
            mode=trade_data["mode"],
            confluence_result=trade_data["confluence_result"],
            bias_direction=trade_data["bias_direction"],
            bias_confidence=trade_data["bias_confidence"],
            stop_loss=trade_data["stop_loss"],
            take_profit=trade_data["take_profit"],
            exit_reason=exit_reason,
            metadata=trade_data["metadata"]
        )
        
        self._trades.append(trade)
        
        # Update daily stats
        await self._update_daily_stats(trade)
        
        # Publish trade log event
        await self._publish(EventType.TRADE_LOG, asdict(trade))
        
        # Save periodically
        if len(self._trades) % 10 == 0:
            await self._save_trades()
    
    async def _on_trade_executed(self, event: Event) -> None:
        """Handle executed trade (alternative to position open/close)."""
        payload = event.payload
        # This can be used for instant execution logging
        pass
    
    async def _on_trade_rejected(self, event: Event) -> None:
        """Log rejected trades."""
        payload = event.payload
        # Could log rejection reasons for analysis
        pass
    
    async def _on_mode_switch(self, event: Event) -> None:
        """Track mode switches for analysis."""
        payload = event.payload
        # Could correlate mode switches with performance
        pass
    
    async def _on_tuning(self, event: Event) -> None:
        """Handle tuning from ManagerAgent."""
        payload = event.payload
        if payload.get("target_agent") == self.name:
            params = payload.get("parameters", {})
            if "optimization_enabled" in params:
                self.optimization_enabled = params["optimization_enabled"]
    
    async def _update_daily_stats(self, trade: TradeRecord) -> None:
        """Update daily statistics."""
        date_key = trade.exit_time.date().isoformat()
        
        if date_key not in self._daily_stats:
            self._daily_stats[date_key] = {
                "trades": [],
                "total_pnl": 0.0,
                "wins": 0,
                "losses": 0
            }
        
        day = self._daily_stats[date_key]
        day["trades"].append(trade)
        day["total_pnl"] += trade.pnl
        if trade.pnl > 0:
            day["wins"] += 1
        else:
            day["losses"] += 1
    
    async def _daily_report_loop(self) -> None:
        """Generate daily reports at end of day."""
        while self._running:
            # Calculate time until next midnight UTC
            now = datetime.utcnow()
            next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            wait_seconds = (next_midnight - now).total_seconds()
            
            await asyncio.sleep(min(wait_seconds, 3600))  # Check at least hourly
            
            # Generate report for yesterday
            yesterday = (now - timedelta(days=1)).date().isoformat()
            if yesterday in self._daily_stats:
                report = await self._generate_daily_report(yesterday)
                await self._save_report(report)
                await self._publish(EventType.DAILY_REPORT, asdict(report))
    
    async def _generate_daily_report(self, date: str) -> DailyReport:
        """Generate comprehensive daily report."""
        day_data = self._daily_stats.get(date, {"trades": []})
        trades = day_data["trades"]
        
        if not trades:
            return DailyReport(
                date=date, total_trades=0, winning_trades=0, losing_trades=0,
                win_rate=0, total_pnl=0, total_pnl_pct=0, avg_win=0, avg_loss=0,
                profit_factor=0, max_drawdown=0, sharpe_ratio=0,
                scalping_trades=0, swing_trades=0, scalping_pnl=0, swing_pnl=0,
                best_trade={}, worst_trade={}, mode_performance={}, symbol_performance={},
                optimization_suggestions=["No trades today"]
            )
        
        # Basic stats
        total_trades = len(trades)
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        winning_trades = len(wins)
        losing_trades = len(losses)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        total_pnl = sum(t.pnl for t in trades)
        
        # P&L stats
        avg_win = np.mean([t.pnl for t in wins]) if wins else 0
        avg_loss = np.mean([t.pnl for t in losses]) if losses else 0
        profit_factor = abs(sum(t.pnl for t in wins) / sum(t.pnl for t in losses)) if losses and sum(t.pnl for t in losses) != 0 else float('inf')
        
        # Returns for Sharpe
        returns = [t.pnl_pct for t in trades]
        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
        
        # Max drawdown
        equity_curve = np.cumsum([t.pnl for t in trades])
        peak = np.maximum.accumulate(equity_curve)
        drawdown = peak - equity_curve
        max_drawdown = np.max(drawdown) if len(drawdown) > 0 else 0
        
        # Mode breakdown
        scalping_trades = [t for t in trades if t.mode == "scalping"]
        swing_trades = [t for t in trades if t.mode == "swing"]
        scalping_pnl = sum(t.pnl for t in scalping_trades)
        swing_pnl = sum(t.pnl for t in swing_trades)
        
        mode_performance = {
            "scalping": {
                "trades": len(scalping_trades),
                "pnl": scalping_pnl,
                "win_rate": len([t for t in scalping_trades if t.pnl > 0]) / max(len(scalping_trades), 1)
            },
            "swing": {
                "trades": len(swing_trades),
                "pnl": swing_pnl,
                "win_rate": len([t for t in swing_trades if t.pnl > 0]) / max(len(swing_trades), 1)
            }
        }
        
        # Symbol breakdown
        symbol_performance = {}
        for trade in trades:
            sym = trade.symbol
            if sym not in symbol_performance:
                symbol_performance[sym] = {"trades": 0, "pnl": 0, "wins": 0}
            symbol_performance[sym]["trades"] += 1
            symbol_performance[sym]["pnl"] += trade.pnl
            if trade.pnl > 0:
                symbol_performance[sym]["wins"] += 1
        
        # Best/worst trades
        best_trade = max(trades, key=lambda t: t.pnl)
        worst_trade = min(trades, key=lambda t: t.pnl)
        
        # Optimization suggestions
        suggestions = self._generate_optimization_suggestions(trades, mode_performance, symbol_performance)
        
        return DailyReport(
            date=date,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl / 10000,  # Would use actual account size
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe,
            scalping_trades=len(scalping_trades),
            swing_trades=len(swing_trades),
            scalping_pnl=scalping_pnl,
            swing_pnl=swing_pnl,
            best_trade=asdict(best_trade),
            worst_trade=asdict(worst_trade),
            mode_performance=mode_performance,
            symbol_performance=symbol_performance,
            optimization_suggestions=suggestions
        )
    
    def _generate_optimization_suggestions(self, trades: List[TradeRecord], 
                                          mode_perf: Dict, symbol_perf: Dict) -> List[str]:
        """Generate optimization suggestions from trade analysis."""
        suggestions = []
        
        # Mode performance
        scalping_wr = mode_perf.get("scalping", {}).get("win_rate", 0)
        swing_wr = mode_perf.get("swing", {}).get("win_rate", 0)
        
        if scalping_wr > swing_wr + 0.15 and mode_perf["scalping"]["trades"] > 10:
            suggestions.append("Consider increasing scalping allocation - higher win rate")
        elif swing_wr > scalping_wr + 0.15 and mode_perf["swing"]["trades"] > 10:
            suggestions.append("Consider increasing swing allocation - higher win rate")
        
        # Symbol performance
        for sym, perf in symbol_perf.items():
            if perf["trades"] >= 5:
                wr = perf["wins"] / perf["trades"]
                if wr < 0.35:
                    suggestions.append(f"Consider avoiding {sym} - win rate {wr:.1%}")
                elif wr > 0.65:
                    suggestions.append(f"Consider increasing size on {sym} - win rate {wr:.1%}")
        
        # Exit reason analysis
        sl_exits = [t for t in trades if t.exit_reason == "sl"]
        tp_exits = [t for t in trades if t.exit_reason == "tp"]
        if len(sl_exits) > len(tp_exits) * 2:
            suggestions.append("Stop losses hitting frequently - consider wider stops or better entries")
        
        # Hold time analysis
        scalping_holds = [t.hold_duration_minutes for t in trades if t.mode == "scalping" and t.hold_duration_minutes]
        if scalping_holds and np.mean(scalping_holds) > 20:
            suggestions.append("Scalping holds too long - consider tighter exits")
        
        return suggestions[:5]  # Top 5 suggestions
    
    async def _optimization_loop(self) -> None:
        """Run periodic strategy optimization."""
        while self._running:
            await asyncio.sleep(3600)  # Check hourly
            
            if not self.optimization_enabled:
                continue
            
            if self._last_optimization and (datetime.utcnow() - self._last_optimization).total_seconds() < self.optimization_interval_hours * 3600:
                continue
            
            if len(self._trades) < self.min_trades_for_optimization:
                continue
            
            await self._run_optimization()
    
    async def _run_optimization(self) -> None:
        """Run parameter optimization using recent trades."""
        # Use last 100 trades for optimization
        recent_trades = self._trades[-100:]
        
        # Define parameter bounds for optimization
        self._parameter_bounds = {
            "bias.min_confidence": (0.5, 0.8),
            "confluence.required_alignment": (2, 4),
            "sizing.max_risk_per_trade": (0.01, 0.03),
            "style.scalping_target_pct": (0.002, 0.005),
            "style.swing_target_pct": (0.008, 0.02),
            "risk.max_portfolio_drawdown": (0.05, 0.15),
        }
        
        # Simple grid search / random search for demonstration
        # In production, would use Bayesian optimization (Optuna, etc.)
        best_params = await self._grid_search_optimization(recent_trades)
        
        if best_params:
            for param, new_value in best_params.items():
                old_value = self._get_current_param(param)
                if abs(new_value - old_value) / max(abs(old_value), 1e-6) > 0.05:  # 5% change threshold
                    result = OptimizationResult(
                        parameter=param,
                        old_value=old_value,
                        new_value=new_value,
                        expected_improvement=0.1,  # Placeholder
                        confidence=0.7,
                        reasoning=f"Optimization based on {len(recent_trades)} recent trades"
                    )
                    self._optimization_results.append(result)
                    
                    # Publish tuning event for target agent
                    agent_name = self._param_to_agent(param)
                    if agent_name:
                        await self._publish(EventType.AGENT_TUNING, {
                            "target_agent": agent_name,
                            "parameters": {param.split(".")[-1]: new_value},
                            "source": "trade_master_optimization"
                        })
        
        self._last_optimization = datetime.utcnow()
        
        # Publish optimization update
        await self._publish(EventType.OPTIMIZATION_UPDATE, {
            "timestamp": self._last_optimization.isoformat(),
            "results": [asdict(r) for r in self._optimization_results[-10:]]
        })
    
    async def _grid_search_optimization(self, trades: List[TradeRecord]) -> Dict[str, float]:
        """Simple grid search for parameter optimization."""
        # This is a simplified version - in production use Optuna or similar
        best_sharpe = -999
        best_params = {}
        
        # Test a few combinations
        for bias_conf in [0.55, 0.6, 0.65, 0.7]:
            for confluence_align in [2, 3]:
                for risk_pct in [0.015, 0.02, 0.025]:
                    # Simulate performance with these params (simplified)
                    sharpe = self._simulate_sharpe(trades, bias_conf, confluence_align, risk_pct)
                    if sharpe > best_sharpe:
                        best_sharpe = sharpe
                        best_params = {
                            "bias.min_confidence": bias_conf,
                            "confluence.required_alignment": confluence_align,
                            "sizing.max_risk_per_trade": risk_pct
                        }
        
        return best_params
    
    def _simulate_sharpe(self, trades: List[TradeRecord], bias_conf: float, 
                        confluence_align: int, risk_pct: float) -> float:
        """Simulate Sharpe ratio with given parameters (simplified)."""
        # Filter trades that would have been taken with these params
        filtered = [
            t for t in trades 
            if t.bias_confidence >= bias_conf 
            and (t.confluence_result in ["strong_bullish", "strong_bearish"] or confluence_align <= 2)
        ]
        
        if len(filtered) < 10:
            return -999
        
        returns = [t.pnl_pct * (risk_pct / 0.02) for t in filtered]  # Scale by risk
        if np.std(returns) == 0:
            return 0
        return np.mean(returns) / np.std(returns) * np.sqrt(252)
    
    def _get_current_param(self, param: str) -> Any:
        """Get current parameter value (would query agent registry in production)."""
        # Placeholder - would integrate with agent registry
        defaults = {
            "bias.min_confidence": 0.6,
            "confluence.required_alignment": 3,
            "sizing.max_risk_per_trade": 0.02,
            "style.scalping_target_pct": 0.003,
            "style.swing_target_pct": 0.01,
            "risk.max_portfolio_drawdown": 0.10,
        }
        return defaults.get(param, 0)
    
    def _param_to_agent(self, param: str) -> Optional[str]:
        """Map parameter to agent name."""
        mapping = {
            "bias.": "BiasDeterminingAgent",
            "confluence.": "MultiTimeframeConfluenceAgent",
            "sizing.": "PositionSizingAgent",
            "style.": "StyleManagingAgent",
            "risk.": "RiskCheckingAgent",
        }
        for prefix, agent in mapping.items():
            if param.startswith(prefix):
                return agent
        return None
    
    async def _save_trades(self) -> None:
        """Save trades to disk."""
        file_path = self.data_dir / f"trades_{datetime.utcnow().date().isoformat()}.json"
        
        # Convert to serializable format
        data = []
        for trade in self._trades:
            d = asdict(trade)
            d["entry_time"] = trade.entry_time.isoformat()
            d["exit_time"] = trade.exit_time.isoformat() if trade.exit_time else None
            data.append(d)
        
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    async def _load_trades(self) -> None:
        """Load trades from disk."""
        for file_path in sorted(self.data_dir.glob("trades_*.json")):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                for d in data:
                    d["entry_time"] = datetime.fromisoformat(d["entry_time"])
                    d["exit_time"] = datetime.fromisoformat(d["exit_time"]) if d["exit_time"] else None
                    trade = TradeRecord(**d)
                    self._trades.append(trade)
            except Exception as e:
                print(f"Error loading {file_path}: {e}")
    
    async def _save_report(self, report: DailyReport) -> None:
        """Save daily report to disk."""
        file_path = self.report_dir / f"daily_report_{report.date}.json"
        with open(file_path, 'w') as f:
            json.dump(asdict(report), f, indent=2, default=str)