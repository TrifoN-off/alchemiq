"""`import alchemiq` must never pull in redis; the subpackage may."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


def test_import_alchemiq_does_not_import_redis() -> None:
    code = (
        "import sys, alchemiq; "
        "leaked = [m for m in sys.modules if m == 'redis' or m.startswith('redis.')]; "
        "assert not leaked, leaked"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_cache_subpackage_is_importable() -> None:
    import alchemiq.cache  # noqa: F401


def test_redis_backend_importable_with_extra() -> None:
    from alchemiq.cache.redis import RedisCache  # noqa: F401


def test_configure_cache_url_without_redis_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import alchemiq
    from alchemiq.cache import reset_cache

    monkeypatch.setitem(sys.modules, "redis", None)  # force ImportError on `import redis`
    monkeypatch.setitem(sys.modules, "redis.asyncio", None)
    sys.modules.pop("alchemiq.cache.redis", None)
    try:
        with pytest.raises(ImportError, match=r"\[redis\]"):
            alchemiq.configure_cache(url="redis://localhost:6379/0")
    finally:
        sys.modules.pop("alchemiq.cache.redis", None)
        reset_cache()


async def test_redis_scan_delete_batches_at_256() -> None:
    """Exercises the len(batch) >= 256 flush path in RedisCache.scan_delete."""
    from alchemiq.cache.redis import RedisCache

    # Build an async generator that yields 257 keys
    async def _scan_iter(match: str):
        for i in range(257):
            yield f"aq:tbl:obj:{i}"

    delete_calls: list[tuple] = []

    async def _delete(*keys: str) -> int:
        delete_calls.append(keys)
        return len(keys)

    redis_mock = MagicMock()
    redis_mock.scan_iter = _scan_iter
    redis_mock.delete = _delete

    cache = RedisCache.__new__(RedisCache)
    cache.default_ttl = 60
    cache.namespace = "aq"
    cache._redis = redis_mock

    await cache.scan_delete("aq:tbl:obj:*")

    # First call should flush the 256-key batch, second the remaining 1
    assert len(delete_calls) == 2
    assert len(delete_calls[0]) == 256
    assert len(delete_calls[1]) == 1
