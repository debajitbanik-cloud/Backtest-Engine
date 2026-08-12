"""
Manager Agent
Orchestrates all sub-agents, tunes parameters, receives daily reports, makes high-level decisions.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path
import json

from core.base_agent import BaseAgent, AgentConfig, AgentStatus
from core.event_bus import EventBus, Event, EventType, event_bus
from core.agent_registry import AgentRegistry, agent_registry


@dataclass
class AgentPerformance:
    """Performance metrics for a sub-agent."""
    agent_name: str
    metric_name: str
    current_value: float
    target_value: float
    trend: str  # improving/degrading/stable
    last_updated: datetime


@dataclass
class TuningDecision:
    """Parameter tuning decision."""
    target_agent: str
    parameter: str
    old_value: Any
    new_value: Any
    reasoning: str
    confidence: float
    timestamp: datetime


class ManagerAgent(BaseAgent):
    """
    Master orchestrator that manages all sub-agents.
    
    Responsibilities:
    - Monitor all agent health and performance
    - Receive daily reports from TradeMasterAgent
    - Tune agent parameters based on performance
    - Coordinate mode switches and risk responses
    - Make high-level strategic decisions
    - Generate manager reports for human oversight
    """
    
    def __init__(self, config: AgentConfig, event_bus: EventBus = None, registry: AgentRegistry = None):
        super().__init__(config, event_bus)
        self.registry = registry or agent_registry
        
        manager_config = config.config.get("manager", {})
        self.report_dir = Path(manager_config.get("report_dir", "reports/manager"))
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.tuning_enabled = manager_config.get("tuning_enabled", True)
        self.tuning_interval_hours = manager_config.get("tuning_interval_hours", 6)
        self.min_confidence_for_tuning = manager_config.get("min_confidence_for_tuning", 0.7)
        
        # State
        self._agent_performance: Dict[str, AgentPerformance] = {}
        self._daily_reports: List[Dict] = []
        self._tuning_history: List[TuningDecision] = []
        self._last_tuning: Optional[datetime] = None
        self._system_mode: str = "normal"  # normal/cautious/aggressive/defensive
        self._pending_decisions: List[Dict] = []
        
        # Subscribe to events
        self.config.subscriptions = [
            EventType.AGENT_HEARTBEAT,
            EventType.AGENT_REGISTERED,
            EventType.DAILY_REPORT,
            EventType.OPTIMIZATION_UPDATE,
            EventType.RISK_ALERT,
            EventType.MODE_SWITCH,
            EventType.LEVERAGE_ADJUSTMENT,
            EventType.SYSTEM_SHUTDOWN,
        ]
    
    async def initialize(self) -> None:
        """Initialize the manager agent."""
        self.status = AgentStatus.RUNNING
        await self._subscribe_to_events()
        
        # Register as orchestrator
        await self._publish(EventType.AGENT_REGISTERED, {
            "agent": self.name,
            "role": "manager",
            "capabilities": ["orchestration", "parameter_tuning", "performance_monitoring", "strategic_decisions"],
            "managed_agents": list(self.registry._agents.keys())
        })
    
    async def start(self) -> None:
        """Start the manager agent."""
        self._running = True
        asyncio.create_task(self._management_loop())
        asyncio.create_task(self._run_heartbeat())
    
    async def stop(self) -> None:
        """Stop the manager agent."""
        self._running = False
        self.status = AgentStatus.STOPPED
        await self._save_state()
    
    async def _handle_event(self, event: Event) -> None:
        """Handle incoming events."""
        self.update_heartbeat()
        
        if event.type == EventType.AGENT_HEARTBEAT:
            await self._on_agent_heartbeat(event)
        elif event.type == EventType.AGENT_REGISTERED:
            await self._on_agent_registered(event)
        elif event.type == EventType.DAILY_REPORT:
            await self._on_daily_report(event)
        elif event.type == EventType.OPTIMIZATION_UPDATE:
            await self._on_optimization_update(event)
        elif event.type == EventType.RISK_ALERT:
            await self._on_risk_alert(event)
        elif event.type == EventType.MODE_SWITCH:
            await self._on_mode_switch(event)
        elif event.type == EventType.LEVERAGE_ADJUSTMENT:
            await self._on_leverage_adjustment(event)
        elif event.type == EventType.SYSTEM_SHUTDOWN:
            await self._on_shutdown(event)
    
    async def _on_agent_heartbeat(self, event: Event) -> None:
        """Track agent health from heartbeats."""
        payload = event.payload
        agent_name = payload.get("agent")
        status = payload.get("status")
        metrics = payload.get("metrics", {})
        
        if agent_name and agent_name != self.name:
            self._agent_performance[agent_name] = AgentPerformance(
                agent_name=agent_name,
                metric_name="health",
                current_value=1.0 if status == "running" else 0.0,
                target_value=1.0,
                trend="stable",
                last_updated=datetime.utcnow()
            )
            
            # Store agent-specific metrics
            for key, value in metrics.items():
                if isinstance(value, (int, float)):
                    metric_name = f"{agent_name}.{key}"
                    self._agent_performance[metric_name] = AgentPerformance(
                        agent_name=agent_name,
                        metric_name=key,
                        current_value=value,
                        target_value=value,  # Would be set based on targets
                        trend="stable",
                        last_updated=datetime.utcnow()
                    )
    
    async def _on_agent_registered(self, event: Event) -> None:
        """Track newly registered agents."""
        payload = event.payload
        agent_name = payload.get("agent")
        capabilities = payload.get("capabilities", [])
        
        print(f"Manager: Agent registered - {agent_name} with capabilities: {capabilities}")
    
    async def _on_daily_report(self, event: Event) -> None:
        """Process daily report from TradeMasterAgent."""
        report = event.payload
        self._daily_reports.append(report)
        
        # Keep last 30 days
        if len(self._daily_reports) > 30:
            self._daily_reports = self._daily_reports[-30:]
        
        # Analyze and potentially tune
        await self._analyze_daily_report(report)
        
        # Generate manager summary
        await self._generate_manager_summary(report)
    
    async def _on_optimization_update(self, event: Event) -> None:
        """Process optimization suggestions from TradeMasterAgent."""
        payload = event.payload
        results = payload.get("results", [])
        
        for result in results:
            param = result.get("parameter")
            new_value = result.get("new_value")
            confidence = result.get("confidence", 0)
            reasoning = result.get("reasoning", "")
            
            if confidence >= self.min_confidence_for_tuning:
                agent_name = self._param_to_agent(param)
                if agent_name:
                    await self._apply_tuning(agent_name, param.split(".")[-1], new_value, reasoning, confidence)
    
    async def _on_risk_alert(self, event: Event) -> None:
        """Handle risk alerts - may trigger system mode change."""
        payload = event.payload
        risk_level = payload.get("risk_level")
        action = payload.get("action")
        symbol = payload.get("symbol")
        
        if risk_level == "critical":
            # Switch to defensive mode
            await self._set_system_mode("defensive", f"Critical risk alert: {payload.get('reasoning')}")
        elif risk_level == "high" and self._system_mode == "normal":
            await self._set_system_mode("cautious", f"High risk alert: {payload.get('reasoning')}")
    
    async def _on_mode_switch(self, event: Event) -> None:
        """Track mode switches from StyleManagingAgent."""
        payload = event.payload
        new_mode = payload.get("new_mode")
        reasoning = payload.get("reasoning")
        
        print(f"Manager: Mode switched to {new_mode} - {reasoning}")
        
        # Could adjust other agents based on mode
        if new_mode == "scalping":
            await self._publish(EventType.AGENT_TUNING, {
                "target_agent": "PositionSizingAgent",
                "parameters": {"default_method": "confluence_weighted"},
                "source": "manager_mode_switch"
            })
        elif new_mode == "swing":
            await self._publish(EventType.AGENT_TUNING, {
                "target_agent": "PositionSizingAgent",
                "parameters": {"default_method": "volatility_adjusted"},
                "source": "manager_mode_switch"
            })
    
    async def _on_leverage_adjustment(self, event: Event) -> None:
        """Track leverage adjustments."""
        payload = event.payload
        symbol = payload.get("symbol")
        new_leverage = payload.get("new_leverage")
        reason = payload.get("reason")
        
        if reason in ["liquidation_risk", "critical_margin"]:
            # Escalate to risk checking
            await self._publish(EventType.RISK_ALERT, {
                "symbol": symbol,
                "risk_level": "high",
                "action": "reduce_leverage",
                "metric": "leverage_adjustment",
                "current_value": new_leverage,
                "threshold": 1.0,
                "reasoning": f"Leverage reduced due to {reason}"
            })
    
    async def _on_shutdown(self, event: Event) -> None:
        """Handle system shutdown."""
        await self._save_state()
        self._running = False
    
    async def _management_loop(self) -> None:
        """Main management loop."""
        while self._running:
            await asyncio.sleep(300)  # Every 5 minutes
            
            await self._check_agent_health()
            await self._evaluate_system_mode()
            
            if self.tuning_enabled and self._should_tune():
                await self._run_tuning_cycle()
            
            await self._publish(EventType.AGENT_HEARTBEAT, {
                "agent": self.name,
                "status": self.status.value,
                "system_mode": self._system_mode,
                "managed_agents": len(self._agent_performance),
                "tuning_count": len(self._tuning_history)
            })
    
    async def _check_agent_health(self) -> None:
        """Check if all agents are healthy."""
        now = datetime.utcnow()
        stale_threshold = timedelta(minutes=5)
        
        for agent_name, perf in self._agent_performance.items():
            if isinstance(perf, AgentPerformance) and perf.metric_name == "health":
                if now - perf.last_updated > stale_threshold:
                    print(f"Manager WARNING: Agent {agent_name} appears stale")
                    # Could trigger restart or alert
    
    async def _evaluate_system_mode(self) -> None:
        """Evaluate and potentially change system mode."""
        # Check recent performance
        if len(self._daily_reports) >= 3:
            recent = self._daily_reports[-3:]
            avg_pnl = sum(r.get("total_pnl", 0) for r in recent) / len(recent)
            avg_win_rate = sum(r.get("win_rate", 0) for r in recent) / len(recent)
            
            if avg_pnl > 0 and avg_win_rate > 0.55 and self._system_mode in ["normal", "cautious"]:
                await self._set_system_mode("aggressive", "Strong recent performance")
            elif avg_pnl < 0 or avg_win_rate < 0.45:
                if self._system_mode in ["normal", "aggressive"]:
                    await self._set_system_mode("cautious", "Weak recent performance")
    
    async def _set_system_mode(self, mode: str, reasoning: str) -> None:
        """Change system-wide trading mode."""
        if mode == self._system_mode:
            return
        
        old_mode = self._system_mode
        self._system_mode = mode
        
        print(f"Manager: System mode changed from {old_mode} to {mode} - {reasoning}")
        
        # Apply mode-specific adjustments
        if mode == "defensive":
            await self._publish(EventType.AGENT_TUNING, {
                "target_agent": "RiskCheckingAgent",
                "parameters": {"max_portfolio_drawdown": 0.05, "max_daily_loss": 0.015},
                "source": "manager_defensive_mode"
            })
            await self._publish(EventType.AGENT_TUNING, {
                "target_agent": "PositionSizingAgent",
                "parameters": {"max_risk_per_trade": 0.01},
                "source": "manager_defensive_mode"
            })
        elif mode == "aggressive":
            await self._publish(EventType.AGENT_TUNING, {
                "target_agent": "RiskCheckingAgent",
                "parameters": {"max_portfolio_drawdown": 0.15, "max_daily_loss": 0.05},
                "source": "manager_aggressive_mode"
            })
            await self._publish(EventType.AGENT_TUNING, {
                "target_agent": "PositionSizingAgent",
                "parameters": {"max_risk_per_trade": 0.03},
                "source": "manager_aggressive_mode"
            })
        elif mode == "cautious":
            await self._publish(EventType.AGENT_TUNING, {
                "target_agent": "RiskCheckingAgent",
                "parameters": {"max_portfolio_drawdown": 0.08, "max_daily_loss": 0.02},
                "source": "manager_cautious_mode"
            })
            await self._publish(EventType.AGENT_TUNING, {
                "target_agent": "PositionSizingAgent",
                "parameters": {"max_risk_per_trade": 0.015},
                "source": "manager_cautious_mode"
            })
        else:  # normal
            await self._publish(EventType.AGENT_TUNING, {
                "target_agent": "RiskCheckingAgent",
                "parameters": {"max_portfolio_drawdown": 0.10, "max_daily_loss": 0.03},
                "source": "manager_normal_mode"
            })
            await self._publish(EventType.AGENT_TUNING, {
                "target_agent": "PositionSizingAgent",
                "parameters": {"max_risk_per_trade": 0.02},
                "source": "manager_normal_mode"
            })
    
    def _should_tune(self) -> bool:
        """Check if tuning cycle should run."""
        if not self._last_tuning:
            return True
        return (datetime.utcnow() - self._last_tuning).total_seconds() > self.tuning_interval_hours * 3600
    
    async def _run_tuning_cycle(self) -> None:
        """Run parameter tuning based on agent performance."""
        self._last_tuning = datetime.utcnow()
        
        # Analyze each agent's performance
        for agent_name, perf in self._agent_performance.items():
            if isinstance(perf, AgentPerformance) and perf.metric_name != "health":
                await self._evaluate_agent_performance(agent_name, perf)
    
    async def _evaluate_agent_performance(self, agent_name: str, perf: AgentPerformance) -> None:
        """Evaluate individual agent performance and tune if needed."""
        # This would contain agent-specific logic
        # For now, just log
        pass
    
    async def _apply_tuning(self, agent_name: str, parameter: str, new_value: Any, 
                           reasoning: str, confidence: float) -> None:
        """Apply parameter tuning to an agent."""
        # Get current value (would query agent in production)
        old_value = None
        
        decision = TuningDecision(
            target_agent=agent_name,
            parameter=parameter,
            old_value=old_value,
            new_value=new_value,
            reasoning=reasoning,
            confidence=confidence,
            timestamp=datetime.utcnow()
        )
        
        self._tuning_history.append(decision)
        if len(self._tuning_history) > 100:
            self._tuning_history = self._tuning_history[-100:]
        
        # Publish tuning event
        await self._publish(EventType.AGENT_TUNING, {
            "target_agent": agent_name,
            "parameters": {parameter: new_value},
            "source": "manager_tuning",
            "reasoning": reasoning,
            "confidence": confidence
        })
        
        print(f"Manager: Tuned {agent_name}.{parameter} = {new_value} (confidence: {confidence:.1%}) - {reasoning}")
    
    def _param_to_agent(self, param: str) -> Optional[str]:
        """Map parameter to agent name."""
        mapping = {
            "bias.": "BiasDeterminingAgent",
            "confluence.": "MultiTimeframeConfluenceAgent",
            "sizing.": "PositionSizingAgent",
            "style.": "StyleManagingAgent",
            "risk.": "RiskCheckingAgent",
            "leverage.": "LeverageAdjustmentAgent",
        }
        for prefix, agent in mapping.items():
            if param.startswith(prefix):
                return agent
        return None
    
    async def _analyze_daily_report(self, report: Dict) -> None:
        """Analyze daily report for insights."""
        win_rate = report.get("win_rate", 0)
        total_pnl = report.get("total_pnl", 0)
        suggestions = report.get("optimization_suggestions", [])
        
        print(f"Manager: Daily report - Win rate: {win_rate:.1%}, PnL: {total_pnl:.2f}")
        for s in suggestions:
            print(f"  Suggestion: {s}")
        
        # Could trigger immediate tuning based on suggestions
        for suggestion in suggestions:
            if "increasing" in suggestion.lower() and "allocation" in suggestion.lower():
                if "scalping" in suggestion.lower():
                    await self._publish(EventType.AGENT_TUNING, {
                        "target_agent": "StyleManagingAgent",
                        "parameters": {"scalping_allocation": 0.6},
                        "source": "manager_daily_analysis"
                    })
    
    async def _generate_manager_summary(self, report: Dict) -> None:
        """Generate manager summary report."""
        summary = {
            "date": datetime.utcnow().date().isoformat(),
            "system_mode": self._system_mode,
            "daily_pnl": report.get("total_pnl", 0),
            "daily_win_rate": report.get("win_rate", 0),
            "agent_health": {
                name: perf.current_value 
                for name, perf in self._agent_performance.items() 
                if isinstance(perf, AgentPerformance) and perf.metric_name == "health"
            },
            "recent_tunings": len([t for t in self._tuning_history 
                                  if (datetime.utcnow() - t.timestamp).total_seconds() < 86400]),
            "open_positions": report.get("total_trades", 0)  # Approximation
        }
        
        # Save to file
        file_path = self.report_dir / f"manager_summary_{summary['date']}.json"
        with open(file_path, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
    
    async def _save_state(self) -> None:
        """Save manager state to disk."""
        state = {
            "system_mode": self._system_mode,
            "tuning_history": [
                {
                    "target_agent": t.target_agent,
                    "parameter": t.parameter,
                    "old_value": t.old_value,
                    "new_value": t.new_value,
                    "reasoning": t.reasoning,
                    "confidence": t.confidence,
                    "timestamp": t.timestamp.isoformat()
                }
                for t in self._tuning_history
            ],
            "agent_performance": {
                name: {
                    "metric_name": p.metric_name,
                    "current_value": p.current_value,
                    "target_value": p.target_value,
                    "trend": p.trend,
                    "last_updated": p.last_updated.isoformat()
                }
                for name, p in self._agent_performance.items()
                if isinstance(p, AgentPerformance)
            }
        }
        
        file_path = self.report_dir / "manager_state.json"
        with open(file_path, 'w') as f:
            json.dump(state, f, indent=2, default=str)