"""
Options Agent
=============
Continuously scans Delta Exchange options for inflated OTM contracts,
computes Greeks and portfolio risk, and publishes option signals.
Can also suggest protective hedges when RiskCheckingAgent requests it.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core.base_agent import BaseAgent, AgentConfig, AgentStatus
from core.event_bus import EventBus, Event, EventType, event_bus
from core.options_engine import OptionsScanner, options_scanner


@dataclass
class OptionsAgentConfig:
    enabled: bool = True
    scan_interval_sec: int = 60
    min_premium_pct: float = 0.25
    min_otm_pct: float = 0.02
    min_days: float = 1
    max_days: float = 30
    top_n_portfolio: int = 5
    hedge_max_premium_pct: float = 0.50


class OptionsAgent(BaseAgent):
    """
    Agent that monitors options markets and emits OPTION_SIGNAL events.
    """

    def __init__(self, config: AgentConfig, event_bus: EventBus = None):
        super().__init__(config, event_bus)

        cfg = config.config.get("options_agent", {})
        self.options_config = OptionsAgentConfig(**cfg)
        self.scanner = OptionsScanner(
            min_premium_pct=self.options_config.min_premium_pct,
            min_otm_pct=self.options_config.min_otm_pct,
            min_days=self.options_config.min_days,
            max_days=self.options_config.max_days,
        )

        self._last_candidates: List[Dict] = []
        self._last_signal: Optional[Dict] = None
        self._last_hedge_suggestion: Optional[Dict] = None
        self._running = False

        self.config.subscriptions = [
            EventType.MARKET_TICK,
            EventType.POSITION_UPDATE,
            EventType.RISK_ALERT,
            EventType.AGENT_TUNING,
        ]

    async def initialize(self) -> None:
        self.status = AgentStatus.RUNNING
        await self._subscribe_to_events()
        await self._publish(EventType.AGENT_REGISTERED, {
            "agent": self.name,
            "capabilities": ["options_scan", "greeks", "portfolio_options_risk", "hedge_suggestion"],
            "config": self.options_config.__dict__,
        })

    async def start(self) -> None:
        self._running = True
        asyncio.create_task(self._scan_loop())
        asyncio.create_task(self._run_heartbeat())

    async def stop(self) -> None:
        self._running = False
        self.status = AgentStatus.STOPPED

    async def _handle_event(self, event: Event) -> None:
        self.update_heartbeat()

        if event.type == EventType.RISK_ALERT:
            await self._on_risk_alert(event.payload)
        elif event.type == EventType.AGENT_TUNING:
            await self._on_tuning(event.payload)

    async def _on_risk_alert(self, payload: Dict[str, Any]) -> None:
        """Generate a protective hedge option suggestion on request."""
        action = payload.get("action")
        if action != "HEDGE":
            return

        symbol = payload.get("symbol", "")
        underlying = symbol.replace("USDT", "").replace("USD", "")
        if not underlying:
            return

        # Find a cheap OTM protective put
        candidates = self.scanner.scan(limit=100)
        puts = [c for c in candidates if c.get("option_type") == "put" and c.get("underlying") == underlying]
        if not puts:
            return

        # Prefer nearest OTM put with lowest premium
        puts.sort(key=lambda x: (x.get("otm_pct", 0), x.get("premium_pct", 0)))
        hedge = puts[0]
        self._last_hedge_suggestion = {
            "intent": "hedge",
            "trigger": payload,
            "suggestion": hedge,
        }
        await self._publish(EventType.OPTION_SIGNAL, {
            "agent": self.name,
            "intent": "hedge",
            "symbol": symbol,
            "suggestion": hedge,
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def _on_tuning(self, payload: Dict[str, Any]) -> None:
        if payload.get("target_agent") == self.name:
            for key, value in payload.get("parameters", {}).items():
                if hasattr(self.options_config, key):
                    setattr(self.options_config, key, value)
            # Rebuild scanner with new params
            self.scanner = OptionsScanner(
                min_premium_pct=self.options_config.min_premium_pct,
                min_otm_pct=self.options_config.min_otm_pct,
                min_days=self.options_config.min_days,
                max_days=self.options_config.max_days,
            )

    async def _scan_loop(self) -> None:
        while self._running:
            try:
                candidates = self.scanner.scan(limit=30)
                self._last_candidates = candidates
                portfolio_greeks = self.scanner.portfolio_greeks(candidates, top_n=self.options_config.top_n_portfolio)
                self._last_signal = {
                    "agent": self.name,
                    "timestamp": datetime.utcnow().isoformat(),
                    "candidate_count": len(candidates),
                    "candidates": candidates[:10],
                    "portfolio_greeks": portfolio_greeks,
                }
                await self._publish(EventType.OPTION_SIGNAL, self._last_signal)
            except Exception as e:
                self._last_signal = {
                    "agent": self.name,
                    "timestamp": datetime.utcnow().isoformat(),
                    "error": str(e),
                }
                await self._publish(EventType.OPTION_SIGNAL, self._last_signal)

            await asyncio.sleep(self.options_config.scan_interval_sec)

    def get_latest_signal(self) -> Optional[Dict]:
        return self._last_signal

    def get_latest_hedge(self) -> Optional[Dict]:
        return self._last_hedge_suggestion
