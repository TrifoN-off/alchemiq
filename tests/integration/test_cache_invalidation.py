from __future__ import annotations

import pytest
import sqlalchemy as sa

from alchemiq import Model, Repository, UnitOfWork
from alchemiq.cache.memory import InMemoryCache
from alchemiq.runtime.session import session_scope
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class IWidget(Model):
    __tablename__ = "cache_inval_widget"
    id: PK[int]
    name: str


async def test_get_pk_caches_and_update_invalidates(configured_db: None) -> None:
    cache = InMemoryCache()
    repo = Repository(IWidget, cache=cache)
    w = await repo.create(name="a")

    assert (await repo.get(id=w.id)).name == "a"  # MISS -> obj key stored
    async with session_scope(write=True) as s:
        await s.execute(sa.text("UPDATE cache_inval_widget SET name='x' WHERE id=:i"), {"i": w.id})
    assert (await repo.get(id=w.id)).name == "a"  # HIT (stale) - proves obj cache

    await repo.update(w.id, name="b")  # invalidate_row post-commit
    assert (await repo.get(id=w.id)).name == "b"  # fresh after invalidation


async def test_invalidation_only_after_uow_commit(configured_db: None) -> None:
    cache = InMemoryCache()
    repo = Repository(IWidget, cache=cache)
    w = await repo.create(name="a")
    await repo.get(id=w.id)  # cache the obj

    try:
        async with UnitOfWork():
            await repo.update(w.id, name="rolled-back")
            raise RuntimeError("abort")
    except RuntimeError:
        pass

    # rollback discarded the invalidation -> obj cache intact, still "a"
    assert (await repo.get(id=w.id)).name == "a"


async def test_manual_cache_clear_and_evict(configured_db: None) -> None:
    cache = InMemoryCache()
    repo = Repository(IWidget, cache=cache)
    w = await repo.create(name="a")
    await repo.get(id=w.id)  # populate obj cache

    await repo.cache_evict(w.id)
    async with session_scope(write=True) as s:
        await s.execute(sa.text("UPDATE cache_inval_widget SET name='z' WHERE id=:i"), {"i": w.id})
    assert (await repo.get(id=w.id)).name == "z"  # evicted -> refetched fresh

    # cache_clear flushes the whole-model cache: a cached list goes fresh after clear
    await repo.all()  # cache the list
    async with session_scope(write=True) as s:
        stmt = sa.text("UPDATE cache_inval_widget SET name='cleared' WHERE id=:i")
        await s.execute(stmt, {"i": w.id})
    await repo.cache_clear()
    assert (await repo.all())[0].name == "cleared"


class _RaisingCache:
    default_ttl = 60
    namespace = "aq"

    async def get(self, key):
        raise RuntimeError("redis down")

    async def set(self, key, value, *, ttl):
        raise RuntimeError("redis down")

    async def delete(self, *keys):
        raise RuntimeError("redis down")

    async def incr(self, key):
        raise RuntimeError("redis down")

    async def scan_delete(self, match):
        raise RuntimeError("redis down")


async def test_write_commits_even_when_cache_raises(configured_db: None) -> None:
    repo = Repository(IWidget, cache=_RaisingCache())
    # post-commit invalidation hits the raising cache -> swallowed (fail-open on writes)
    w = await repo.create(name="persisted")
    # the row must have landed despite the cache outage
    fetched = await Repository(IWidget).get_or_none(id=w.id)
    assert fetched is not None
    assert fetched.name == "persisted"
