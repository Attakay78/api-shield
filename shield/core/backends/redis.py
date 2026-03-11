"""Redis backend for api-shield.

Uses ``redis.asyncio`` for all I/O.  Supports multi-instance deployments
via pub/sub on the ``shield:changes`` channel.

Key schema
----------
``shield:state:{path}``        — JSON-serialized ``RouteState``
``shield:route-index``         — Redis Set of all registered route paths
                                  (replaces dangerous ``KEYS`` scans with safe
                                  O(N) ``SMEMBERS`` that does not block the server)
``shield:audit``               — Redis list, newest-first (LPUSH + LTRIM to 1000)
``shield:audit:path:{path}``   — Per-path audit list for O(limit) filtered queries
                                  instead of fetching all 1000 entries to filter in Python
``shield:changes``             — pub/sub channel for live state updates

Performance notes
-----------------
*  ``list_states()`` uses ``SMEMBERS shield:route-index`` + ``MGET`` instead
   of ``KEYS shield:state:*``.  ``KEYS`` is an O(keyspace) blocking command
   that freezes Redis on production instances; ``SMEMBERS`` on a dedicated
   set is safe and equally fast.
*  ``set_state()`` / ``delete_state()`` maintain the route-index atomically
   via pipeline so the set and the state key are always in sync.
*  ``get_audit_log(path=X)`` reads directly from ``shield:audit:path:X``
   instead of fetching up to 1000 global entries and filtering in Python.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool

from shield.core.backends.base import ShieldBackend
from shield.core.models import AuditEntry, RouteState

logger = logging.getLogger(__name__)

_AUDIT_KEY = "shield:audit"
_ROUTE_INDEX_KEY = "shield:route-index"
_CHANGES_CHANNEL = "shield:changes"
_MAX_AUDIT_ENTRIES = 1000


def _state_key(path: str) -> str:
    return f"shield:state:{path}"


def _audit_path_key(path: str) -> str:
    """Per-path audit list key for O(limit) filtered audit queries."""
    return f"shield:audit:path:{path}"


class RedisBackend(ShieldBackend):
    """Backend that stores all state in Redis.

    Supports multi-instance deployments.  ``subscribe()`` uses Redis
    pub/sub so that state changes made by one instance are immediately
    visible in the dashboard on any other instance.

    Parameters
    ----------
    url:
        Redis connection URL (e.g. ``"redis://localhost:6379/0"``).
    """

    def __init__(self, url: str = "redis://localhost:6379/0") -> None:
        self._pool = ConnectionPool.from_url(url, decode_responses=True)

    def _client(self) -> aioredis.Redis:
        """Return a Redis client using the shared connection pool."""
        return aioredis.Redis(connection_pool=self._pool)

    # ------------------------------------------------------------------
    # ShieldBackend interface
    # ------------------------------------------------------------------

    async def get_state(self, path: str) -> RouteState:
        """Return the current state for *path*.

        Raises ``KeyError`` if no state has been registered for *path*.
        """
        try:
            async with self._client() as r:
                raw = await r.get(_state_key(path))
        except Exception as exc:
            logger.error("shield: redis get_state error for %r: %s", path, exc)
            raise

        if raw is None:
            raise KeyError(f"No state registered for path {path!r}")
        return RouteState.model_validate(json.loads(raw))

    async def set_state(self, path: str, state: RouteState) -> None:
        """Persist *state* for *path*, update the route-index, and publish to
        ``shield:changes``.

        The state key and the route-index entry are written atomically in a
        single pipeline so ``list_states()`` can never see a state key that
        is missing from the index (or vice-versa).
        """
        payload = state.model_dump_json()
        try:
            async with self._client() as r:
                pipe = r.pipeline()
                pipe.set(_state_key(path), payload)
                pipe.sadd(_ROUTE_INDEX_KEY, path)
                pipe.publish(_CHANGES_CHANNEL, payload)
                await pipe.execute()
        except Exception as exc:
            logger.error("shield: redis set_state error for %r: %s", path, exc)
            raise

    async def delete_state(self, path: str) -> None:
        """Remove state for *path* and remove it from the route-index.

        No-op if *path* is not registered.
        """
        try:
            async with self._client() as r:
                pipe = r.pipeline()
                pipe.delete(_state_key(path))
                pipe.srem(_ROUTE_INDEX_KEY, path)
                await pipe.execute()
        except Exception as exc:
            logger.error("shield: redis delete_state error: %s", exc)
            raise

    async def list_states(self) -> list[RouteState]:
        """Return all registered route states.

        Uses ``SMEMBERS shield:route-index`` + ``MGET`` instead of the
        dangerous ``KEYS shield:state:*`` pattern.  ``KEYS`` is an O(keyspace)
        blocking command that can freeze a busy Redis server; ``SMEMBERS`` on
        the dedicated route-index set is safe to use in production.
        """
        try:
            async with self._client() as r:
                paths: set[str] = await r.smembers(_ROUTE_INDEX_KEY)  # type: ignore[misc]
                if not paths:
                    return []
                keys = [_state_key(p) for p in paths]
                values: list[str | None] = await r.mget(*keys)
        except Exception as exc:
            logger.error("shield: redis list_states error: %s", exc)
            raise

        states: list[RouteState] = []
        for raw in values:
            if raw is not None:
                states.append(RouteState.model_validate(json.loads(raw)))
        return states

    async def write_audit(self, entry: AuditEntry) -> None:
        """Append *entry* to both the global audit list and the per-path list.

        Both lists are capped at 1000 entries via ``LTRIM``.  Writing to a
        per-path list means ``get_audit_log(path=X)`` can fetch exactly the
        required entries directly — no full-list fetch-then-filter in Python.
        """
        payload = entry.model_dump_json()
        path_key = _audit_path_key(entry.path)
        try:
            async with self._client() as r:
                pipe = r.pipeline()
                # Global audit list (for unfiltered queries).
                pipe.lpush(_AUDIT_KEY, payload)
                pipe.ltrim(_AUDIT_KEY, 0, _MAX_AUDIT_ENTRIES - 1)
                # Per-path audit list (for filtered queries — O(limit) instead
                # of O(1000) fetch-then-filter).
                pipe.lpush(path_key, payload)
                pipe.ltrim(path_key, 0, _MAX_AUDIT_ENTRIES - 1)
                await pipe.execute()
        except Exception as exc:
            logger.error("shield: redis write_audit error: %s", exc)
            raise

    async def get_audit_log(self, path: str | None = None, limit: int = 100) -> list[AuditEntry]:
        """Return audit entries, newest first.

        When *path* is provided the per-path list is used — fetches exactly
        *limit* entries via a single ``LRANGE`` call, eliminating the
        fetch-all-then-filter pattern of the previous implementation.
        """
        try:
            async with self._client() as r:
                if path is not None:
                    # Per-path list: fetch exactly what we need — O(limit).
                    raws: list[str] = await r.lrange(  # type: ignore[misc]
                        _audit_path_key(path), 0, limit - 1
                    )
                else:
                    # Global list: all entries newest-first.
                    raws = await r.lrange(_AUDIT_KEY, 0, limit - 1)  # type: ignore[misc]
        except Exception as exc:
            logger.error("shield: redis get_audit_log error: %s", exc)
            raise

        return [AuditEntry.model_validate(json.loads(raw)) for raw in raws]

    async def subscribe(self) -> AsyncIterator[RouteState]:
        """Yield ``RouteState`` objects as they are updated via pub/sub."""
        async with self._client() as r:
            async with r.pubsub() as pubsub:
                await pubsub.subscribe(_CHANGES_CHANNEL)
                async for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    try:
                        state = RouteState.model_validate(json.loads(message["data"]))
                        yield state
                    except Exception as exc:
                        logger.warning("shield: redis subscribe parse error: %s", exc)
