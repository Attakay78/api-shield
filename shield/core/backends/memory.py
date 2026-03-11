"""In-process memory backend for api-shield."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from collections.abc import AsyncIterator

from shield.core.backends.base import ShieldBackend
from shield.core.models import AuditEntry, RouteState

_MAX_AUDIT_ENTRIES = 1000


class MemoryBackend(ShieldBackend):
    """Backend that stores all state in-process.

    Default backend. Ideal for single-instance apps and testing.
    State is lost when the process restarts.

    Audit log is stored in a ``deque`` (O(1) append/evict) with a parallel
    per-path index (``dict[path, list[AuditEntry]]``) so that filtered
    queries — ``get_audit_log(path=...)`` — are O(k) where k is the number
    of entries for that specific path, not O(total entries).
    """

    def __init__(self) -> None:
        self._states: dict[str, RouteState] = {}
        # Ordered audit log — deque gives O(1) append and O(1) popleft eviction.
        self._audit: deque[AuditEntry] = deque()
        # Per-path index for O(1)-lookup filtered audit queries.
        self._audit_by_path: defaultdict[str, list[AuditEntry]] = defaultdict(list)
        self._subscribers: list[asyncio.Queue[RouteState]] = []

    async def get_state(self, path: str) -> RouteState:
        """Return the current state for *path*.

        Raises ``KeyError`` if no state has been registered for *path*.
        """
        try:
            return self._states[path]
        except KeyError:
            raise KeyError(f"No state registered for path {path!r}")

    async def set_state(self, path: str, state: RouteState) -> None:
        """Persist *state* for *path* and notify any subscribers."""
        self._states[path] = state
        for queue in self._subscribers:
            await queue.put(state)

    async def delete_state(self, path: str) -> None:
        """Remove state for *path*. No-op if not registered."""
        self._states.pop(path, None)

    async def list_states(self) -> list[RouteState]:
        """Return all registered route states."""
        return list(self._states.values())

    async def write_audit(self, entry: AuditEntry) -> None:
        """Append *entry* to the audit log, capping at 1000 entries.

        When the cap is reached the oldest entry is evicted from both the
        ordered deque and the per-path index in O(1) / O(k) time respectively,
        where k is the number of entries for the evicted path (≪ total entries).
        """
        if len(self._audit) >= _MAX_AUDIT_ENTRIES:
            evicted = self._audit.popleft()
            # Clean up the per-path index for the evicted entry.
            path_list = self._audit_by_path.get(evicted.path)
            if path_list:
                try:
                    path_list.remove(evicted)
                except ValueError:
                    pass

        self._audit.append(entry)
        self._audit_by_path[entry.path].append(entry)

    async def get_audit_log(self, path: str | None = None, limit: int = 100) -> list[AuditEntry]:
        """Return audit entries, newest first, optionally filtered by *path*.

        When *path* is provided the per-path index is used — O(k) where k is
        the number of entries for that route — instead of scanning all 1000
        entries (O(N)).
        """
        if path is None:
            return list(reversed(self._audit))[:limit]
        path_entries = self._audit_by_path.get(path, [])
        return list(reversed(path_entries))[:limit]

    async def subscribe(self) -> AsyncIterator[RouteState]:
        """Yield ``RouteState`` objects as they are updated."""
        queue: asyncio.Queue[RouteState] = asyncio.Queue()
        self._subscribers.append(queue)
        try:
            while True:
                state = await queue.get()
                yield state
        finally:
            self._subscribers.remove(queue)
