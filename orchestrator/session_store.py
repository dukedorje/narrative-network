"""GatewaySessionStore — Redis-backed session persistence for the gateway.

Serialises OrchestratorSession state to JSON so sessions survive pod restarts
and are shared across HPA-scaled replicas. Falls back to an in-memory dict
when Redis is unavailable.

Key layout (Redis):
    gateway:session:<session_id>  ->  JSON blob of serialisable session fields

TTL is set on every write and refreshed on every read, so active sessions
never expire mid-traversal.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

log = logging.getLogger(__name__)

_REDIS_KEY_PREFIX = "gateway:session:"


def _session_key(session_id: str) -> str:
    return f"{_REDIS_KEY_PREFIX}{session_id}"


# ---------------------------------------------------------------------------
# Serialisation helpers for OrchestratorSession
# ---------------------------------------------------------------------------

def _serialise_session(session: Any) -> dict:
    """Extract the JSON-serialisable fields from an OrchestratorSession."""
    return {
        "session_id": session.session_id,
        "state": session.state.value,
        "player_path": list(session.player_path),
        "path_embeddings": [list(e) for e in session.path_embeddings],
        "prior_narrative": session.prior_narrative,
        "current_node_id": session.current_node_id,
        "choice_cards": session.choice_cards,
        "top_k_chunks": session.top_k_chunks,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def _restore_session(data: dict, dendrite: Any, metagraph: Any, safety_guard: Any) -> Any:
    """Reconstruct an OrchestratorSession from a serialised dict.

    Non-serialisable runtime dependencies (dendrite, metagraph, safety_guard)
    are re-attached from the caller's scope.
    """
    from orchestrator.session import OrchestratorSession, SessionState

    session = OrchestratorSession(
        session_id=data["session_id"],
        dendrite=dendrite,
        metagraph=metagraph,
        safety_guard=safety_guard,
        top_k_chunks=data.get("top_k_chunks", 5),
    )
    session.state = SessionState(data["state"])
    session.player_path = data.get("player_path", [])
    session.path_embeddings = data.get("path_embeddings", [])
    session.prior_narrative = data.get("prior_narrative", "")
    session.current_node_id = data.get("current_node_id")
    session.choice_cards = data.get("choice_cards")
    session.created_at = data.get("created_at", time.time())
    session.updated_at = data.get("updated_at", time.time())
    return session


# ---------------------------------------------------------------------------
# GatewaySessionStore
# ---------------------------------------------------------------------------

class GatewaySessionStore:
    """Async store for gateway sessions.

    Wraps OrchestratorSession state as JSON in Redis (or in-memory fallback).
    TTL is refreshed on every successful get/set so active sessions stay alive.

    Parameters
    ----------
    redis_url:
        Redis connection URL, e.g. ``"redis://redis:6379/0"``.
        Pass ``None`` to force in-memory mode (useful in tests / dev).
    ttl:
        Session TTL in seconds. Refreshed on every access.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        ttl: int = 1800,
    ) -> None:
        self._redis_url = redis_url
        self._ttl = ttl
        self._redis: Any = None
        self._use_redis = redis_url is not None
        # Fallback: (data_dict, expires_at_monotonic)
        self._memory: dict[str, tuple[dict, float]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Attempt Redis connection; silently degrade to in-memory on failure."""
        if not self._use_redis:
            log.info("GatewaySessionStore: using in-memory fallback (no Redis URL)")
            return
        try:
            import redis.asyncio as aioredis  # type: ignore[import]

            self._redis = await aioredis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            await self._redis.ping()
            log.info("GatewaySessionStore connected to Redis at %s", self._redis_url)
        except Exception as exc:
            log.warning(
                "GatewaySessionStore: Redis unavailable (%s) — falling back to in-memory", exc
            )
            self._redis = None
            self._use_redis = False

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    # ------------------------------------------------------------------
    # Core get/set for OrchestratorSession objects
    # ------------------------------------------------------------------

    async def get(
        self,
        session_id: str,
        *,
        dendrite: Any = None,
        metagraph: Any = None,
        safety_guard: Any = None,
    ) -> Any | None:
        """Return a restored OrchestratorSession or None if missing/expired.

        Also refreshes the TTL so active sessions don't expire mid-traversal.
        """
        data = await self._get_raw(session_id)
        if data is None:
            return None
        # Refresh TTL on access
        await self._set_raw(session_id, data)
        return _restore_session(data, dendrite, metagraph, safety_guard)

    async def set(self, session: Any) -> None:
        """Serialise and persist an OrchestratorSession."""
        data = _serialise_session(session)
        await self._set_raw(session.session_id, data)

    async def delete(self, session_id: str) -> None:
        if self._redis is not None:
            await self._redis.delete(_session_key(session_id))
            return
        self._memory.pop(session_id, None)

    async def exists(self, session_id: str) -> bool:
        return await self._get_raw(session_id) is not None

    # ------------------------------------------------------------------
    # Dict-style store for dev app (stores plain dicts, not OrchestratorSession)
    # ------------------------------------------------------------------

    async def get_dict(self, session_id: str) -> dict | None:
        """Return raw session dict or None. Refreshes TTL on access."""
        data = await self._get_raw(session_id)
        if data is None:
            return None
        await self._set_raw(session_id, data)
        return data

    async def set_dict(self, session_id: str, data: dict) -> None:
        """Persist a plain dict session."""
        await self._set_raw(session_id, data)

    # ------------------------------------------------------------------
    # Active session counting (for /healthz)
    # ------------------------------------------------------------------

    async def count_active(self) -> int:
        """Return number of sessions with state == 'active'."""
        if self._redis is not None:
            keys = await self._redis.keys(f"{_REDIS_KEY_PREFIX}*")
            count = 0
            for key in keys:
                raw = await self._redis.get(key)
                if raw:
                    try:
                        data = json.loads(raw)
                        if data.get("state") == "active":
                            count += 1
                    except (json.JSONDecodeError, TypeError):
                        pass
            return count
        now = time.monotonic()
        return sum(
            1
            for data, exp in self._memory.values()
            if (exp is None or now < exp) and data.get("state") == "active"
        )

    async def count_total(self) -> int:
        """Return total number of live sessions."""
        if self._redis is not None:
            keys = await self._redis.keys(f"{_REDIS_KEY_PREFIX}*")
            return len(keys)
        now = time.monotonic()
        return sum(1 for _, exp in self._memory.values() if exp is None or now < exp)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_raw(self, session_id: str) -> dict | None:
        if self._redis is not None:
            raw = await self._redis.get(_session_key(session_id))
            if raw is None:
                return None
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return None

        entry = self._memory.get(session_id)
        if entry is None:
            return None
        data, expires_at = entry
        if time.monotonic() > expires_at:
            del self._memory[session_id]
            return None
        return data

    async def _set_raw(self, session_id: str, data: dict) -> None:
        serialized = json.dumps(data)
        if self._redis is not None:
            await self._redis.set(_session_key(session_id), serialized, ex=self._ttl)
            return
        expires_at = time.monotonic() + self._ttl
        self._memory[session_id] = (data, expires_at)
