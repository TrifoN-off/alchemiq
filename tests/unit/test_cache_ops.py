from __future__ import annotations

import pytest

from alchemiq.cache import keys, ops
from alchemiq.cache.memory import InMemoryCache
from alchemiq.query.queryset import QuerySet
from tests.unit._cache_models import KItem

pytestmark = pytest.mark.unit


class RaisingCache:
    default_ttl = 60
    namespace = "aq"

    async def get(self, key):
        raise RuntimeError("down")

    async def set(self, key, value, *, ttl):
        raise RuntimeError("down")

    async def delete(self, *keys):
        raise RuntimeError("down")

    async def incr(self, key):
        raise RuntimeError("down")

    async def scan_delete(self, match):
        raise RuntimeError("down")


def _qs(cache):
    return QuerySet(KItem, cache=cache, cache_ttl=None)


async def test_read_list_miss_then_hit() -> None:
    cache = InMemoryCache()
    qs = _qs(cache)
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        return [KItem(id=1, name="a", secret="x")]

    first = await ops.read_list(qs, fetch)
    second = await ops.read_list(qs, fetch)
    assert calls["n"] == 1  # second served from cache
    assert [r.name for r in first] == [r.name for r in second] == ["a"]


async def test_read_list_fail_open() -> None:
    qs = _qs(RaisingCache())
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        return [KItem(id=1, name="a", secret="x")]

    assert [r.name for r in await ops.read_list(qs, fetch)] == ["a"]
    assert [r.name for r in await ops.read_list(qs, fetch)] == ["a"]
    assert calls["n"] == 2  # no caching, fetch each time, never raises


async def test_read_count_round_trips() -> None:
    cache = InMemoryCache()
    qs = _qs(cache)
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        return 7

    assert await ops.read_count(qs, fetch) == 7
    assert await ops.read_count(qs, fetch) == 7
    assert calls["n"] == 1


async def test_read_exists_round_trips() -> None:
    cache = InMemoryCache()
    qs = _qs(cache)
    calls = {"n": 0}

    async def fetch():
        calls["n"] += 1
        return True

    assert await ops.read_exists(qs, fetch) is True
    assert await ops.read_exists(qs, fetch) is True
    assert calls["n"] == 1


async def test_read_obj_stores_under_obj_key() -> None:
    cache = InMemoryCache()

    async def fetch():
        return KItem(id=5, name="e", secret="x")

    got = await ops.read_obj(KItem, cache, 60, 5, fetch)
    assert got.name == "e"
    assert await cache.get(keys.obj_key("aq", "cache_kitem", 5)) is not None


async def test_read_obj_propagates_fetch_exception() -> None:
    cache = InMemoryCache()

    class NotFound(Exception):
        pass

    async def fetch():
        raise NotFound("gone")

    with pytest.raises(NotFound):
        await ops.read_obj(KItem, cache, 60, 99, fetch)
    assert await cache.get(keys.obj_key("aq", "cache_kitem", 99)) is None


async def test_invalidate_row_bumps_version_and_drops_obj() -> None:
    cache = InMemoryCache()
    await cache.set(keys.obj_key("aq", "cache_kitem", 5), "{}", ttl=60)
    await ops.invalidate_row(cache, KItem, 5)
    assert await cache.get(keys.version_key("aq", "cache_kitem")) == "1"
    assert await cache.get(keys.obj_key("aq", "cache_kitem", 5)) is None


async def test_invalidate_model_bumps_version_and_scans_obj() -> None:
    cache = InMemoryCache()
    await cache.set(keys.obj_key("aq", "cache_kitem", 1), "{}", ttl=60)
    await cache.set(keys.obj_key("aq", "cache_kitem", 2), "{}", ttl=60)
    await ops.invalidate_model(cache, KItem)
    assert await cache.get(keys.version_key("aq", "cache_kitem")) == "1"
    assert await cache.get(keys.obj_key("aq", "cache_kitem", 1)) is None
    assert await cache.get(keys.obj_key("aq", "cache_kitem", 2)) is None


async def test_delete_fail_open() -> None:
    """_delete exception branch is swallowed (fail-open)."""
    await ops._delete(RaisingCache(), "aq:x:obj:1")  # must not raise


async def test_incr_fail_open() -> None:
    """_incr exception branch is swallowed (fail-open)."""
    await ops._incr(RaisingCache(), "aq:x:ver")  # must not raise


async def test_scan_delete_fail_open() -> None:
    """_scan_delete exception branch is swallowed (fail-open)."""
    await ops._scan_delete(RaisingCache(), "aq:x:obj:*")  # must not raise
