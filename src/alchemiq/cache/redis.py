"""Redis-backed cache implementation (requires the ``[redis]`` extra)."""

from __future__ import annotations

from typing import Any

from redis.asyncio import Redis  # ty: ignore[unresolved-import]


class RedisCache:
    """``CacheBackend`` backed by ``redis.asyncio``.

    Built automatically by :func:`.configure_cache` when a Redis ``url`` is supplied.
    Requires the ``[redis]`` extra (``pip install 'alchemiq[redis]'``).  The caller
    owns the connection lifecycle; call ``aclose()`` on shutdown.
    """

    def __init__(
        self, url: str, *, default_ttl: int = 60, namespace: str = "aq", **redis_kw: Any
    ) -> None:
        self.default_ttl = default_ttl
        self.namespace = namespace
        self._redis = Redis.from_url(url, decode_responses=True, **redis_kw)

    async def get(self, key: str) -> str | None:
        """Return the string value, or ``None`` on miss."""
        return await self._redis.get(key)  # ty: ignore[invalid-return-type]

    async def set(self, key: str, value: str, *, ttl: int) -> None:
        """Store ``value``; a zero TTL omits the expiry (key persists indefinitely)."""
        await self._redis.set(key, value, ex=ttl or None)

    async def delete(self, *keys: str) -> None:
        """Delete one or more keys; no-op when the key list is empty."""
        if keys:
            await self._redis.delete(*keys)

    async def incr(self, key: str) -> int:
        """Atomically increment a Redis integer counter and return the new value."""
        return int(await self._redis.incr(key))  # ty: ignore[invalid-await]

    async def scan_delete(self, match: str) -> None:
        """Delete all keys matching a glob pattern, streaming via SCAN in batches of 256."""
        batch: list[str] = []
        async for key in self._redis.scan_iter(match=match):
            batch.append(key)
            if len(batch) >= 256:
                await self._redis.delete(*batch)
                batch = []
        if batch:
            await self._redis.delete(*batch)

    async def aclose(self) -> None:
        """Close the underlying Redis connection pool."""
        await self._redis.aclose()
