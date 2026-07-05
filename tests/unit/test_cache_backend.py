from __future__ import annotations

import pytest

from alchemiq.cache import (
    CacheBackend,
    InMemoryCache,
    configure_cache,
    get_cache,
    reset_cache,
)
from alchemiq.exceptions import ConfigError

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_cache()
    yield
    reset_cache()


async def test_inmemory_get_set_delete() -> None:
    c = InMemoryCache()
    assert await c.get("k") is None
    await c.set("k", "v", ttl=60)
    assert await c.get("k") == "v"
    await c.delete("k")
    assert await c.get("k") is None


async def test_inmemory_incr_creates_then_increments() -> None:
    c = InMemoryCache()
    assert await c.incr("n") == 1
    assert await c.incr("n") == 2
    assert await c.get("n") == "2"


async def test_inmemory_ttl_expiry() -> None:
    c = InMemoryCache()
    await c.set("k", "v", ttl=0)  # 0 -> immediately expired / no expiry sentinel
    # ttl=0 means "no TTL" by convention; use a tiny positive ttl with a patched clock instead:
    import alchemiq.cache.memory as mem

    now = [1000.0]
    monkey = mem.time.monotonic
    mem.time.monotonic = lambda: now[0]  # type: ignore[assignment]
    try:
        await c.set("e", "v", ttl=10)
        assert await c.get("e") == "v"
        now[0] = 1011.0
        assert await c.get("e") is None
    finally:
        mem.time.monotonic = monkey  # type: ignore[assignment]


async def test_inmemory_scan_delete_glob() -> None:
    c = InMemoryCache()
    await c.set("aq:users:obj:1", "a", ttl=60)
    await c.set("aq:users:obj:2", "b", ttl=60)
    await c.set("aq:users:ver", "5", ttl=60)
    await c.scan_delete("aq:users:obj:*")
    assert await c.get("aq:users:obj:1") is None
    assert await c.get("aq:users:obj:2") is None
    assert await c.get("aq:users:ver") == "5"  # untouched


def test_inmemory_satisfies_protocol() -> None:
    assert isinstance(InMemoryCache(), CacheBackend)


def test_registry_backend_path() -> None:
    backend = InMemoryCache(default_ttl=30, namespace="x")
    configure_cache(backend=backend)
    assert get_cache() is backend
    assert get_cache().default_ttl == 30
    reset_cache()
    assert get_cache() is None


def test_registry_requires_url_or_backend() -> None:
    with pytest.raises(ConfigError, match="url=|backend="):
        configure_cache()
