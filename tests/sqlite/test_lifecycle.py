"""Soft-delete, optimistic locking, and signals on SQLite."""

from __future__ import annotations

import pytest

import alchemiq
from alchemiq import QuerySet, Repository
from alchemiq.exceptions import NotFoundError
from alchemiq.signals import clear, post_create
from tests.sqlite._models import SqSignal, SqSoft, SqVersioned


@pytest.fixture(autouse=True)
def _clear_signals():
    clear()
    yield
    clear()


async def test_soft_delete_hides_restore_returns(sqlite_db) -> None:
    repo = Repository(SqSoft)
    await repo.create(id=1, name="row")
    await repo.delete(1)
    with pytest.raises(NotFoundError):
        await repo.get(id=1)
    tombstones = await QuerySet(SqSoft).only_deleted().all()
    assert [t.id for t in tombstones] == [1]
    restored = await repo.restore(1)
    assert restored.id == 1
    assert await QuerySet(SqSoft).filter(id=1).exists() is True


async def test_optimistic_locking_conflict(sqlite_db) -> None:
    repo = Repository(SqVersioned)
    obj = await repo.create(id=1, name="v1")
    assert alchemiq.version_of(obj) == 1
    await repo.update(1, expected_version=1, name="v2")
    with pytest.raises(alchemiq.ConcurrentModificationError):
        await repo.update(1, expected_version=1, name="v3")


async def test_post_create_signal_fires(sqlite_db) -> None:
    seen: list[int] = []

    @post_create(SqSignal)
    async def _handler(instance, **kwargs) -> None:
        seen.append(instance.id)

    await Repository(SqSignal).create(id=7, name="ping")
    assert seen == [7]
