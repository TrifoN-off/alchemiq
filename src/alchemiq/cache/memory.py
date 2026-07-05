"""In-process cache backend backed by a plain dict."""

from __future__ import annotations

import fnmatch
import time


class InMemoryCache:
    """Pure-Python :class:`.CacheBackend` for tests and small single-process apps.

    Backed by a plain ``dict``; no external dependencies.  TTL is enforced lazily
    on ``get``.  Counter keys (used by the version-invalidation scheme) never expire.

    E.g.::

        from alchemiq.cache import InMemoryCache, configure_cache

        configure_cache(backend=InMemoryCache(default_ttl=120, namespace="myapp"))

    .. note::

        Not safe for use across multiple processes or workers - use :func:`.configure_cache`
        with a Redis ``url`` for multi-process deployments.
    """

    def __init__(self, *, default_ttl: int = 60, namespace: str = "aq") -> None:
        self.default_ttl = default_ttl
        self.namespace = namespace
        self._store: dict[str, tuple[str, float | None]] = {}

    async def get(self, key: str) -> str | None:
        """Return the cached value, or ``None`` on miss or TTL expiry (lazy eviction)."""
        item = self._store.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at is not None and time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: str, *, ttl: int) -> None:
        """Store ``value`` under ``key``; a zero TTL means no expiry."""
        expires_at = time.monotonic() + ttl if ttl else None
        self._store[key] = (value, expires_at)

    async def delete(self, *keys: str) -> None:
        """Remove one or more keys; silently ignores missing keys."""
        for key in keys:
            self._store.pop(key, None)

    async def incr(self, key: str) -> int:
        """Increment an integer counter, starting at 1 for a new key; never expires."""
        current = await self.get(key)
        nxt = (int(current) + 1) if current is not None else 1
        self._store[key] = (str(nxt), None)  # version keys never expire
        return nxt

    async def scan_delete(self, match: str) -> None:
        """Delete all keys matching a glob pattern."""
        for key in [k for k in self._store if fnmatch.fnmatch(k, match)]:
            self._store.pop(key, None)
