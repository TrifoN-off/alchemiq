"""Read-through and invalidation helpers used by the QuerySet cache layer.

All backend calls are fail-open: errors are logged and the operation proceeds
without cache (never raises to the caller).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from alchemiq.cache import keys, serialize

if TYPE_CHECKING:
    from alchemiq.cache.backend import CacheBackend
    from alchemiq.query.queryset import QuerySet

logger = logging.getLogger("alchemiq.cache")


async def _get(cache: CacheBackend, key: str) -> str | None:
    try:
        return await cache.get(key)
    except Exception:  # noqa: BLE001
        logger.warning("cache get failed for %s", key, exc_info=True)
        return None


async def _set(cache: CacheBackend, key: str, value: str, ttl: int) -> None:
    try:
        await cache.set(key, value, ttl=ttl)
    except Exception:  # noqa: BLE001
        logger.warning("cache set failed for %s", key, exc_info=True)


async def _delete(cache: CacheBackend, *ks: str) -> None:
    try:
        await cache.delete(*ks)
    except Exception:  # noqa: BLE001
        logger.warning("cache delete failed for %s", ks, exc_info=True)


async def _incr(cache: CacheBackend, key: str) -> None:
    try:
        await cache.incr(key)
    except Exception:  # noqa: BLE001
        logger.warning("cache incr failed for %s", key, exc_info=True)


async def _scan_delete(cache: CacheBackend, match: str) -> None:
    try:
        await cache.scan_delete(match)
    except Exception:  # noqa: BLE001
        logger.warning("cache scan_delete failed for %s", match, exc_info=True)


def effective_ttl(qs: QuerySet) -> int:
    """Return the per-queryset TTL override, or the backend's default."""
    return qs._cache_ttl if qs._cache_ttl is not None else qs._cache.default_ttl


async def _version(cache: CacheBackend, ns: str, table: str) -> int:
    raw = await _get(cache, keys.version_key(ns, table))
    return int(raw) if raw is not None else 0


async def read_list(qs: QuerySet, fetch: Callable[[], Awaitable[list[Any]]]) -> list[Any]:
    """Read-through for list queries; key incorporates the table version counter."""
    cache, ns, table = qs._cache, qs._cache.namespace, qs.model.__tablename__  # ty: ignore[unresolved-attribute]
    ver = await _version(cache, ns, table)
    key = keys.query_key(ns, table, ver, keys.query_fingerprint(qs))
    hit = await _get(cache, key)
    if hit is not None:
        return serialize.decode_rows(qs.model, hit)
    rows = await fetch()
    await _set(cache, key, serialize.encode_rows(rows), effective_ttl(qs))
    return rows


async def read_count(qs: QuerySet, fetch: Callable[[], Awaitable[int]]) -> int:
    """Read-through for count queries; key incorporates the table version counter."""
    cache, ns, table = qs._cache, qs._cache.namespace, qs.model.__tablename__  # ty: ignore[unresolved-attribute]
    ver = await _version(cache, ns, table)
    key = keys.count_key(ns, table, ver, keys.query_fingerprint(qs, scalar=True))
    hit = await _get(cache, key)
    if hit is not None:
        return serialize.decode_int(hit)
    value = await fetch()
    await _set(cache, key, serialize.encode_int(value), effective_ttl(qs))
    return value


async def read_exists(qs: QuerySet, fetch: Callable[[], Awaitable[bool]]) -> bool:
    """Read-through for exists queries; key incorporates the table version counter."""
    cache, ns, table = qs._cache, qs._cache.namespace, qs.model.__tablename__  # ty: ignore[unresolved-attribute]
    ver = await _version(cache, ns, table)
    key = keys.exists_key(ns, table, ver, keys.query_fingerprint(qs, scalar=True))
    hit = await _get(cache, key)
    if hit is not None:
        return serialize.decode_bool(hit)
    value = await fetch()
    await _set(cache, key, serialize.encode_bool(value), effective_ttl(qs))
    return value


async def read_obj(
    model: type,
    cache: CacheBackend,
    ttl: int,
    pk: object,
    fetch: Callable[[], Awaitable[Any]],
) -> Any:
    """Read-through for single-row lookup by primary key.

    Propagates ``NotFoundError`` from ``fetch`` without caching a miss.
    """
    ns, table = cache.namespace, model.__tablename__  # ty: ignore[unresolved-attribute]
    key = keys.obj_key(ns, table, pk)
    hit = await _get(cache, key)
    if hit is not None:
        return serialize.decode_row(model, hit)
    obj = await fetch()  # may raise NotFoundError - propagate, do not cache
    await _set(cache, key, serialize.encode_row(obj), ttl)
    return obj


async def bump_version(cache: CacheBackend, model: type) -> None:
    """Increment the table version counter, invalidating all version-keyed query caches."""
    await _incr(cache, keys.version_key(cache.namespace, model.__tablename__))  # ty: ignore[unresolved-attribute]


async def invalidate_row(cache: CacheBackend, model: type, pk: object) -> None:
    """Bump the version counter and delete the single-row cache entry for ``pk``."""
    ns, table = cache.namespace, model.__tablename__  # ty: ignore[unresolved-attribute]
    await _incr(cache, keys.version_key(ns, table))
    await _delete(cache, keys.obj_key(ns, table, pk))


async def invalidate_model(cache: CacheBackend, model: type) -> None:
    """Bump the version counter and delete all single-row entries for the model."""
    ns, table = cache.namespace, model.__tablename__  # ty: ignore[unresolved-attribute]
    await _incr(cache, keys.version_key(ns, table))
    await _scan_delete(cache, keys.obj_key(ns, table, "*"))
