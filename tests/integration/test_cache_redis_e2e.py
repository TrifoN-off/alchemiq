from __future__ import annotations

import pytest

from alchemiq import Model, Repository
from alchemiq.cache.backend import get_cache
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class RWidget(Model):
    __tablename__ = "cache_redis_widget"
    id: PK[int]
    name: str


async def test_redis_get_all_count_and_invalidate(
    configured_db: None, configured_cache: None
) -> None:
    repo = Repository(RWidget, cache=True)  # uses the global RedisCache
    a = await repo.create(name="a")

    assert (await repo.get(id=a.id)).name == "a"  # obj cache
    assert [w.name for w in await repo.all()] == ["a"]  # list cache
    assert await repo.count() == 1  # count cache

    cache = get_cache()
    assert await cache.get(f"aq:cache_redis_widget:obj:{a.id}") is not None

    await repo.update(a.id, name="b")  # post-commit invalidate_row
    assert (await repo.get(id=a.id)).name == "b"
    assert await repo.count() == 1
