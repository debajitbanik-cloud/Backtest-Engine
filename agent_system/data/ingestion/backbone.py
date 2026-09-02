"""
Event Backbone — Redis Streams for durable, replayable event transport.
"""
from __future__ import annotations

import json
from decimal import Decimal
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Set
from dataclasses import dataclass

import redis.asyncio as redis
from redis.asyncio import Redis

from shared.domain import MarketData, Order, Fill, Position, Signal, ExecutionIntent


def _serialize_payload(payload: Dict) -> Dict:
    """Flatten non-primitive values to JSON strings for Redis streams."""
    def _convert(value: Any) -> Any:
        if isinstance(value, (str, bytes, int, float)):
            return value
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return json.dumps(_serialize_payload(value), default=str)
        if isinstance(value, (list, tuple)):
            return json.dumps(value, default=str)
        if value is None:
            return ""
        return json.dumps(value, default=str)
    return {k: _convert(v) for k, v in payload.items()}


# Stream names
STREAM_MARKET_TICKS = "market:ticks"
STREAM_MARKET_CANDLES = "market:candles"
STREAM_ORDERS = "execution:orders"
STREAM_FILLS = "execution:fills"
STREAM_POSITIONS = "execution:positions"
STREAM_SIGNALS = "signals:raw"
STREAM_INTENTS = "execution:intents"
STREAM_RISK_EVENTS = "risk:events"
STREAM_AGENT_EVENTS = "agent:events"


@dataclass
class StreamEvent:
    """Wrapper for stream events with metadata."""
    stream: str
    id: str
    timestamp: datetime
    payload: Dict[str, Any]
    metadata: Dict[str, Any] = None


class EventBackbone:
    """
    Redis Streams-based event backbone for durable, replayable event transport.
    Supports consumer groups for exactly-once processing.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        max_stream_length: int = 100000,
        consumer_group: str = "trading-system",
        consumer_name: str = "worker-1",
    ):
        self.redis_url = redis_url
        self.max_stream_length = max_stream_length
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name
        self._redis: Optional[Redis] = None
        self._handlers: Dict[str, List[Callable]] = {}

    async def connect(self) -> None:
        """Initialize Redis connection and create consumer groups."""
        self._redis = redis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        await self._create_consumer_groups()

    async def disconnect(self) -> None:
        if self._redis:
            await self._redis.close()

    async def _create_consumer_groups(self) -> None:
        """Create consumer groups for all streams."""
        streams = [
            STREAM_MARKET_TICKS,
            STREAM_MARKET_CANDLES,
            STREAM_ORDERS,
            STREAM_FILLS,
            STREAM_POSITIONS,
            STREAM_SIGNALS,
            STREAM_INTENTS,
            STREAM_RISK_EVENTS,
            STREAM_AGENT_EVENTS,
        ]
        for stream in streams:
            try:
                await self._redis.xgroup_create(
                    stream,
                    self.consumer_group,
                    id="0",
                    mkstream=True,
                )
            except redis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise

    # ── Publishing ─────────────────────────────────────────────────────────────

    async def publish_tick(self, tick: Any) -> str:
        """Publish a market tick."""
        return await self._publish(STREAM_MARKET_TICKS, {
            "type": "tick",
            "data": tick if isinstance(tick, dict) else tick.__dict__ if hasattr(tick, "__dict__") else str(tick),
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def publish_candle(self, candle: Any) -> str:
        """Publish a market candle."""
        return await self._publish(STREAM_MARKET_CANDLES, {
            "type": "candle",
            "data": candle if isinstance(candle, dict) else candle.__dict__ if hasattr(candle, "__dict__") else str(candle),
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def publish_order(self, order: Any) -> str:
        """Publish an order event."""
        return await self._publish(STREAM_ORDERS, {
            "type": "order",
            "data": order if isinstance(order, dict) else order.__dict__ if hasattr(order, "__dict__") else str(order),
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def publish_fill(self, fill: Any) -> str:
        """Publish a fill event."""
        return await self._publish(STREAM_FILLS, {
            "type": "fill",
            "data": fill if isinstance(fill, dict) else fill.__dict__ if hasattr(fill, "__dict__") else str(fill),
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def publish_position(self, position: Any) -> str:
        """Publish a position update."""
        return await self._publish(STREAM_POSITIONS, {
            "type": "position",
            "data": position if isinstance(position, dict) else position.__dict__ if hasattr(position, "__dict__") else str(position),
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def publish_signal(self, signal: Any) -> str:
        """Publish a trading signal."""
        return await self._publish(STREAM_SIGNALS, {
            "type": "signal",
            "data": signal if isinstance(signal, dict) else signal.__dict__ if hasattr(signal, "__dict__") else str(signal),
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def publish_intent(self, intent: Any) -> str:
        """Publish an execution intent."""
        return await self._publish(STREAM_INTENTS, {
            "type": "intent",
            "data": intent if isinstance(intent, dict) else intent.__dict__ if hasattr(intent, "__dict__") else str(intent),
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def publish_risk_event(self, event_type: str, payload: Dict) -> str:
        """Publish a risk event."""
        return await self._publish(STREAM_RISK_EVENTS, {
            "type": event_type,
            "data": payload,
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def publish_agent_event(self, agent: str, event_type: str, payload: Dict) -> str:
        """Publish an agent lifecycle event."""
        return await self._publish(STREAM_AGENT_EVENTS, {
            "agent": agent,
            "type": event_type,
            "data": payload,
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def _publish(self, stream: str, payload: Dict) -> str:
        """Internal publish to stream with auto-trimming."""
        if not self._redis:
            raise RuntimeError("EventBackbone not connected")
        event_id = await self._redis.xadd(
            stream,
            _serialize_payload(payload),
            maxlen=self.max_stream_length,
            approximate=True,
        )
        return event_id

    # ── Consuming ──────────────────────────────────────────────────────────────

    def subscribe(self, stream: str, handler: Callable) -> None:
        """Register a handler for a stream."""
        if stream not in self._handlers:
            self._handlers[stream] = []
        self._handlers[stream].append(handler)

    async def consume(
        self,
        streams: List[str],
        count: int = 100,
        block_ms: int = 5000,
    ) -> AsyncIterator[StreamEvent]:
        """Consume events from streams as a consumer group."""
        if not self._redis:
            raise RuntimeError("EventBackbone not connected")

        stream_ids = {stream: ">" for stream in streams}

        while True:
            try:
                results = await self._redis.xreadgroup(
                    self.consumer_group,
                    self.consumer_name,
                    {s: ">" for s in streams},
                    count=count,
                    block=block_ms,
                )

                if not results:
                    continue

                for stream, messages in results:
                    for msg_id, fields in messages:
                        # Convert fields back to proper types
                        payload = {k: json.loads(v) if v.startswith("{") or v.startswith("[") else v for k, v in fields.items()}
                        yield StreamEvent(
                            stream=stream,
                            id=msg_id,
                            timestamp=datetime.utcnow(),
                            payload=payload,
                            metadata={"stream": stream, "message_id": msg_id},
                        )

                        # Acknowledge
                        await self._redis.xack(stream, self.consumer_group, msg_id)

            except redis.ResponseError as e:
                if "NOGROUP" in str(e):
                    await self._create_consumer_groups()
                else:
                    raise
            except Exception as e:
                print(f"Consume error: {e}")
                await asyncio.sleep(1)

    async def read_recent(
        self,
        stream: str,
        count: int = 100,
    ) -> List[Dict]:
        """Read recent messages from a stream (for debugging/replay)."""
        if not self._redis:
            raise RuntimeError("EventBackbone not connected")
        messages = await self._redis.xrevrange(stream, count=count)
        return [{"id": msg_id, **fields} for msg_id, fields in messages]

    async def get_stream_length(self, stream: str) -> int:
        """Get the length of a stream."""
        if not self._redis:
            raise RuntimeError("EventBackbone not connected")
        return await self._redis.xlen(stream)


# Global event backbone
_event_backbone: Optional[EventBackbone] = None


async def get_event_backbone(
    redis_url: str = "redis://localhost:6379/0",
) -> EventBackbone:
    global _event_backbone
    if _event_backbone is None:
        _event_backbone = EventBackbone(redis_url)
        await _event_backbone.connect()
    return _event_backbone


import asyncio