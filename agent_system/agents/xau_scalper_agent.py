"""
XAU Scalper Agent
=================
Consumes the optional 0xagarg/xau-ai-trading-bot repo (or fallback logic)
to generate short-term XAUUSD scalp signals.
"""
from __future__ import annotations
import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core.base_agent import BaseAgent, AgentConfig, AgentStatus
from core.event_bus import EventBus, Event, EventType, event_bus
from data.xau_ai_integration import xau_ai_integration


@dataclass
class XAUScalperConfig:
    enabled: bool = True
    symbol: str = "XAUTUSDT"
    timeframes: List[str] = field(default_factory=lambda: ["1m", "5m"])
    min_confidence: float = 0.65
    cooldown_seconds: int = 60
    max_history: int = 500


class XAUScalperAgent(BaseAgent):
    """
    Agent that produces short-term XAUUSD scalp signals.
    """

    def __init__(self, config: AgentConfig, event_bus: EventBus = None):
        super().__init__(config, event_bus)

        cfg = config.config.get("xau_scalper", {})
        self.scalp_config = XAUScalperConfig(**cfg)
        self.candles: Dict[str, deque] = {
            tf: deque(maxlen=self.scalp_config.max_history)
            for tf in self.scalp_config.timeframes
        }
        self.last_signal: Optional[Dict] = None
        self.signal_history: deque = deque(maxlen=50)
        self.cooldown_until = datetime.utcnow()
        self._running = False

        self.config.subscriptions = [
            EventType.MARKET_CANDLE,
            EventType.MODE_SWITCH,
            EventType.AGENT_TUNING,
        ]

    async def initialize(self) -> None:
        self.status = AgentStatus.RUNNING
        await self._subscribe_to_events()
        await self._publish(EventType.AGENT_REGISTERED, {
            "agent": self.name,
            "capabilities": ["xau_scalping", "xau_signal_generation"],
            "config": self.scalp_config.__dict__,
            "repo_available": xau_ai_integration.available,
        })

    async def start(self) -> None:
        self._running = True
        asyncio.create_task(self._run_heartbeat())

    async def stop(self) -> None:
        self._running = False
        self.status = AgentStatus.STOPPED

    async def _handle_event(self, event: Event) -> None:
        self.update_heartbeat()

        if event.type == EventType.MARKET_CANDLE:
            await self._on_candle(event.payload)
        elif event.type == EventType.MODE_SWITCH:
            await self._on_mode_switch(event.payload)
        elif event.type == EventType.AGENT_TUNING:
            await self._on_tuning(event.payload)

    async def _on_candle(self, payload: Dict[str, Any]) -> None:
        symbol = payload.get("symbol")
        tf = payload.get("timeframe")
        candle = payload.get("candle")

        if symbol != self.scalp_config.symbol or tf not in self.candles:
            return

        self.candles[tf].append(candle)
        await self._evaluate()

    async def _on_mode_switch(self, payload: Dict[str, Any]) -> None:
        mode = payload.get("mode")
        if mode == "scalping":
            self.scalp_config.min_confidence = max(0.55, self.scalp_config.min_confidence - 0.05)
        elif mode == "swing":
            self.scalp_config.min_confidence = min(0.85, self.scalp_config.min_confidence + 0.05)

    async def _on_tuning(self, payload: Dict[str, Any]) -> None:
        if payload.get("target_agent") == self.name:
            for key, value in payload.get("parameters", {}).items():
                if hasattr(self.scalp_config, key):
                    setattr(self.scalp_config, key, value)
            self.candles = {
                tf: deque(maxlen=self.scalp_config.max_history)
                for tf in self.scalp_config.timeframes
            }

    async def _evaluate(self) -> None:
        if datetime.utcnow() < self.cooldown_until:
            return

        if len(self.candles["1m"]) < 30 or len(self.candles["5m"]) < 20:
            return

        signal = xau_ai_integration.get_scalp_signal(
            list(self.candles["1m"]),
            list(self.candles["5m"]),
        )

        if not signal or signal.get("direction") == "flat":
            return

        if signal.get("confidence", 0) < self.scalp_config.min_confidence:
            return

        self.last_signal = signal
        self.signal_history.append(signal)
        self.cooldown_until = datetime.utcnow() + timedelta(
            seconds=self.scalp_config.cooldown_seconds
        )

        # Publish dedicated XAU scalper signal
        await self._publish(EventType.XAU_SCALP_SIGNAL, {
            "agent": self.name,
            **signal,
        })

        # Also publish as BIAS_SIGNAL for TimeframeRecommendationAgent aggregation
        await self._publish(EventType.BIAS_SIGNAL, {
            "symbol": self.scalp_config.symbol,
            "direction": "bullish" if signal["direction"] == "long" else "bearish",
            "confidence": signal["confidence"],
            "timeframe": signal.get("timeframe", "1m"),
            "indicators": {
                "entry": signal.get("entry"),
                "stop_loss": signal.get("stop_loss"),
                "take_profit": signal.get("take_profit"),
                "atr": signal.get("atr"),
                "regime": signal.get("regime"),
                "source": "XAUScalperAgent",
            },
            "reasoning": signal.get("reason", ""),
        })

    def get_latest_signal(self) -> Optional[Dict]:
        return self.last_signal

    def get_signal_history(self) -> List[Dict]:
        return list(self.signal_history)
