import pytest

from alchemiq import Model, UnitOfWork
from alchemiq.runtime.session import session_scope
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class UowRow(Model):
    __tablename__ = "uow_row"
    id: PK[int]
    name: str


async def _count() -> int:
    from sqlalchemy import func, select

    async with session_scope(write=False) as s:
        return int((await s.execute(select(func.count()).select_from(UowRow))).scalar_one())


async def test_commit_on_clean_exit(configured_db):
    async with UnitOfWork() as uow:
        uow.session.add(UowRow(id=1, name="a"))
    assert await _count() == 1


async def test_rollback_on_exception(configured_db):
    with pytest.raises(RuntimeError):
        async with UnitOfWork() as uow:
            uow.session.add(UowRow(id=2, name="b"))
            await uow.session.flush()
            raise RuntimeError("boom")
    assert await _count() == 0


async def test_savepoint_partial_rollback(configured_db):
    async with UnitOfWork() as uow:
        uow.session.add(UowRow(id=3, name="keep"))
        await uow.session.flush()
        with pytest.raises(RuntimeError):
            async with uow.savepoint():
                uow.session.add(UowRow(id=4, name="drop"))
                await uow.session.flush()
                raise RuntimeError("inner")
    # outer committed id=3; savepoint rolled back id=4
    assert await _count() == 1


async def test_reentrant_inner_does_not_commit(configured_db):
    async with UnitOfWork() as outer:
        outer.session.add(UowRow(id=5, name="x"))
        async with UnitOfWork() as inner:
            assert inner.session is outer.session  # joined
            inner.session.add(UowRow(id=6, name="y"))
        # inner exit must NOT have committed yet
        assert await _count_in() == 0
    assert await _count() == 2  # outer commit persisted both


async def test_joined_commit_and_rollback_raise(configured_db):
    async with UnitOfWork():
        async with UnitOfWork() as inner:
            with pytest.raises(RuntimeError):
                await inner.commit()
            with pytest.raises(RuntimeError):
                await inner.rollback()


async def _count_in() -> int:
    from sqlalchemy import func, select

    from alchemiq.runtime.engine import require_sessionmaker

    # fresh isolated session - cannot see uncommitted data (READ COMMITTED)
    factory = require_sessionmaker()
    async with factory() as s:
        return int((await s.execute(select(func.count()).select_from(UowRow))).scalar_one())
