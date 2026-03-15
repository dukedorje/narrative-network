"""Session store with Redis backend and in-memory fallback.

Stores arbitrary JSON-serialisable session data keyed by session_id.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

log = logging.getLogger(__name__)


class SessionStore:
    """Async key-value store for session data.

    Uses Redis when a valid *redis_url* is supplied; falls back to an
    in-memory dict otherwise.

    Parameters
    ----------
    redis_url:
        Redis connection URL, e.g. "redis://localhost:6379/0".
        Pass None to force in-memory mode.
    default_ttl:
        Default TTL in seconds for stored sessions.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        default_ttl: int = 3600,
    ) -> None:
        self.redis_url = redis_url
        self.default_ttl = default_ttl
        self._redis = None
        self._memory: dict[str, tuple[Any, float | None]] = {}  # value, expires_at
        self._use_redis = redis_url is not None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Attempt Redis connection; silently fall back to in-memory on failure."""
        if not self._use_redis:
            return
        try:
            import redis.asyncio as aioredis  # type: ignore
            self._redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            await self._redis.ping()
            log.info("SessionStore connected to Redis at %s", self.redis_url)
        except Exception as exc:
            log.warning(
                "Redis unavailable (%s) — falling back to in-memory session store", exc
            )
            self._redis = None
            self._use_redis = False

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    async def get(self, session_id: str) -> Any | None:
        """Return deserialized session data or None if missing/expired."""
        if self._redis is not None:
            raw = await self._redis.get(session_id)
            if raw is None:
                return None
            return json.loads(raw)

        # In-memory
        entry = self._memory.get(session_id)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and time.monotonic() > expires_at:
            del self._memory[session_id]
            return None
        return value

    async def set(
        self,
        session_id: str,
        data: Any,
        ttl: int | None = None,
    ) -> None:
        """Persist *data* under *session_id* with optional TTL override."""
        effective_ttl = ttl if ttl is not None else self.default_ttl
        serialized = json.dumps(data)

        if self._redis is not None:
            await self._redis.set(session_id, serialized, ex=effective_ttl)
            return

        expires_at = time.monotonic() + effective_ttl if effective_ttl > 0 else None
        self._memory[session_id] = (data, expires_at)

    async def delete(self, session_id: str) -> None:
        """Remove a session entry."""
        if self._redis is not None:
            await self._redis.delete(session_id)
            return
        self._memory.pop(session_id, None)

    async def exists(self, session_id: str) -> bool:
        """Return True if the session exists and has not expired."""
        return await self.get(session_id) is not None

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    async def get_field(self, session_id: str, field: str, default: Any = None) -> Any:
        """Get a single field from a session dict."""
        data = await self.get(session_id)
        if not isinstance(data, dict):
            return default
        return data.get(field, default)

    async def update_field(self, session_id: str, field: str, value: Any) -> None:
        """Merge a single field into an existing session dict."""
        data = await self.get(session_id) or {}
        if not isinstance(data, dict):
            data = {}
        data[field] = value
        await self.set(session_id, data)

    def _prune_memory(self) -> None:
        """Remove expired entries from in-memory store."""
        now = time.monotonic()
        expired = [
            k for k, (_, exp) in self._memory.items() if exp is not None and now > exp
        ]
        for k in expired:
            del self._memory[k]
