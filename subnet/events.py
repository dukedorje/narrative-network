"""EventBus — Redis pub/sub event bus for Narrative Network observability.

Publishes structured JSON events to Redis channels. Falls back to
in-memory asyncio.Queue when Redis is unavailable (single-process dev mode).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import AsyncIterator

log = logging.getLogger(__name__)

FIREHOSE_CHANNEL = "nn:events"
BUFFER_KEY = "nn:events:buffer"
BUFFER_MAX_SIZE = 1000


@dataclass
class Event:
    """A single observability event published by any component."""

    event_type: str  # e.g. "validator.scoring"
    source: str  # e.g. "validator", "miner-2", "gateway"
    payload: dict  # event-specific data
    correlation_id: str = ""  # groups related events (epoch ID or session ID)
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str | bytes) -> Event:
        if isinstance(data, bytes):
            data = data.decode()
        return cls(**json.loads(data))

    @property
    def component_channel(self) -> str:
        """Return the component-specific Redis channel for this event."""
        base = self.source.split("-")[0]  # "miner-2" -> "miner"
        if base == "miner":
            parts = self.source.split("-")
            if len(parts) > 1:
                return f"nn:events:miner:{parts[1]}"
        return f"nn:events:{base}"


class EventBus:
    """Redis pub/sub event bus for Narrative Network observability.

    Falls back to in-memory asyncio.Queue when Redis is unavailable
    (single-process dev mode via `just gateway`).
    """

    def __init__(self, redis_url: str | None = None):
        self._redis_url = redis_url
        self._redis = None
        self._memory_queues: list[asyncio.Queue] = []
        self._connected = False

    async def connect(self) -> None:
        """Connect to Redis. No-op if redis_url is None."""
        if not self._redis_url:
            log.info("EventBus: no REDIS_URL, using in-memory fallback")
            return
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(self._redis_url)
            await self._redis.ping()
            self._connected = True
            log.info("EventBus: connected to Redis at %s", self._redis_url)
        except Exception as exc:
            log.warning(
                "EventBus: Redis connection failed (%s), using in-memory fallback", exc
            )
            self._redis = None

    async def publish(self, event: Event) -> None:
        """Publish event to Redis pub/sub + buffer, or in-memory queues."""
        event_json = event.to_json()

        if self._redis and self._connected:
            pipe = self._redis.pipeline()
            pipe.publish(FIREHOSE_CHANNEL, event_json)
            pipe.publish(event.component_channel, event_json)
            pipe.rpush(BUFFER_KEY, event_json)
            pipe.ltrim(BUFFER_KEY, -BUFFER_MAX_SIZE, -1)
            await pipe.execute()
        else:
            for q in self._memory_queues:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass

    async def subscribe(
        self, channels: list[str] | None = None
    ) -> AsyncIterator[Event]:
        """Yield events from Redis pub/sub or in-memory queue."""
        if channels is None:
            channels = [FIREHOSE_CHANNEL]

        if self._redis and self._connected:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(*channels)
            try:
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            yield Event.from_json(message["data"])
                        except (json.JSONDecodeError, TypeError):
                            continue
            finally:
                await pubsub.unsubscribe(*channels)
                await pubsub.close()
        else:
            q: asyncio.Queue[Event] = asyncio.Queue(maxsize=1000)
            self._memory_queues.append(q)
            try:
                while True:
                    event = await q.get()
                    yield event
            finally:
                self._memory_queues.remove(q)

    async def get_recent(self, limit: int = 50) -> list[Event]:
        """Get recent events from the Redis buffer."""
        if self._redis and self._connected:
            raw = await self._redis.lrange(BUFFER_KEY, -limit, -1)
            events = []
            for item in raw:
                try:
                    events.append(Event.from_json(item))
                except (json.JSONDecodeError, TypeError):
                    continue
            return events
        return []

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()


# ── Convenience publish helpers ──────────────────────────────────────

_bus: EventBus | None = None


async def get_event_bus(redis_url: str | None = None) -> EventBus:
    """Get or create the singleton EventBus."""
    global _bus
    if _bus is None:
        _bus = EventBus(redis_url)
        await _bus.connect()
    return _bus


async def emit(
    event_type: str,
    source: str,
    payload: dict,
    correlation_id: str = "",
) -> None:
    """Convenience: publish an event to the global bus."""
    if _bus is not None:
        await _bus.publish(
            Event(
                event_type=event_type,
                source=source,
                payload=payload,
                correlation_id=correlation_id,
            )
        )
