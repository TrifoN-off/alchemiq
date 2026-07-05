from __future__ import annotations

import pytest
import sqlalchemy as sa

from alchemiq import Model, Repository
from alchemiq.cache.memory import InMemoryCache
from alchemiq.query.queryset import QuerySet
from alchemiq.runtime.session import session_scope
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class CWidget(Model):
    __tablename__ = "cache_read_widget"
    id: PK[int]
    name: str


async def test_all_caches_and_serves_stale_until_invalidated(configured_db: None) -> None:
    cache = InMemoryCache()
    await Repository(CWidget).create(name="one")  # seed via plain (cache-less) repo

    first = await QuerySet(CWidget, cache=cache).all()
    assert [w.name for w in first] == ["one"]

    # mutate out-of-band (raw SQL, no invalidation) -> a cache HIT must still return the stale value
    async with session_scope(write=True) as s:
        await s.execute(sa.text("UPDATE cache_read_widget SET name = 'two'"))

    assert [w.name for w in await QuerySet(CWidget, cache=cache).all()] == ["one"]


async def test_mass_update_invalidates_after_commit(configured_db: None) -> None:
    cache = InMemoryCache()
    await Repository(CWidget).create(name="a")
    await QuerySet(CWidget, cache=cache).all()  # populate the list cache

    # mass update carries the cache -> enqueues invalidate_model, drained AFTER the autocommit
    await QuerySet(CWidget, cache=cache).filter(name="a").update(name="b")

    assert [w.name for w in await QuerySet(CWidget, cache=cache).all()] == ["b"]  # fresh
