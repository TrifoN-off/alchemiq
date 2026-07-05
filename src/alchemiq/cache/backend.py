"""Cache backend protocol and process-global registry."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from alchemiq.exceptions import ConfigError


@runtime_checkable
class CacheBackend(Protocol):
    """Structural protocol for cache backends.

    Implemented by :class:`.InMemoryCache` (core, no extra) and ``RedisCache``
    (requires the ``[redis]`` extra, built automatically by :func:`.configure_cache`
    when a Redis ``url`` is supplied).

    Any object that exposes ``default_ttl``, ``namespace``, and the five async methods
    below satisfies this protocol (``isinstance`` check via ``@runtime_checkable``).

    .. seealso:: :func:`.configure_cache` - register a backend process-globally.
    """

    default_ttl: int
    namespace: str

    async def get(self, key: str) -> str | None:
        """Return the cached string, or ``None`` on miss or expiry."""
        ...

    async def set(self, key: str, value: str, *, ttl: int) -> None:
        """Store ``value`` under ``key`` with a TTL in seconds."""
        ...

    async def delete(self, *keys: str) -> None:
        """Delete one or more keys; no-ops on missing keys."""
        ...

    async def incr(self, key: str) -> int:
        """Atomically increment an integer counter and return the new value."""
        ...

    async def scan_delete(self, match: str) -> None:
        """Delete all keys matching a glob pattern."""
        ...


_cache: CacheBackend | None = None


def configure_cache(
    url: str | None = None,
    *,
    backend: CacheBackend | None = None,
    default_ttl: int = 60,
    namespace: str = "aq",
    **redis_kw: Any,
) -> None:
    """Set the process-global cache backend.

    Pass an explicit ``backend`` instance, or a Redis connection ``url`` (requires the
    ``[redis]`` extra). Only one may be provided.  Call :func:`.reset_cache` to clear
    the global backend (useful in tests).

    E.g.::

        from alchemiq.cache import InMemoryCache, configure_cache, reset_cache

        # in-process cache (no dependencies):
        configure_cache(backend=InMemoryCache(default_ttl=120))

        # Redis (requires [redis] extra):
        configure_cache(url="redis://localhost:6379/0")

    :param url: Redis connection URL; builds a :class:`.CacheBackend` backed by
        ``redis.asyncio``.  Requires ``pip install 'alchemiq[redis]'``.
    :param backend: A :class:`.CacheBackend` instance to use directly.  When given,
        ``default_ttl`` and ``namespace`` are ignored.
    :param default_ttl: Default TTL in seconds for Redis-built backends (default 60).
    :param namespace: Key prefix for Redis-built backends (default ``"aq"``).
    :raises ConfigError: if neither ``url`` nor ``backend`` is provided.
    :raises ImportError: if ``url`` is given but the ``[redis]`` extra is not installed.

    .. seealso:: :class:`.InMemoryCache` - zero-dependency backend for tests.
    """
    global _cache
    if backend is not None:
        _cache = backend
        return
    if url is not None:
        try:
            from alchemiq.cache.redis import RedisCache  # ty: ignore[unresolved-import]
        except ImportError as e:
            raise ImportError(
                "Redis caching requires the [redis] extra: pip install 'alchemiq[redis]'"
            ) from e
        _cache = RedisCache(url, default_ttl=default_ttl, namespace=namespace, **redis_kw)
        return
    raise ConfigError("configure_cache() requires either url= or backend=")


def get_cache() -> CacheBackend | None:
    """Return the active global cache backend, or ``None`` if not configured."""
    return _cache


def reset_cache() -> None:
    """Clear the global cache backend.

    Intended for teardown and test isolation.  Mirrors ``runtime.dispose()``.
    """
    global _cache
    _cache = None
