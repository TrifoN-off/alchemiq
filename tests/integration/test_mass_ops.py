import pytest

from alchemiq import Model
from alchemiq.exceptions import QueryError
from alchemiq.query import QuerySet
from alchemiq.runtime.session import session_scope
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class MassRow(Model):
    __tablename__ = "mass_row"
    id: PK[int]
    name: str
    active: bool


async def _seed() -> None:
    async with session_scope(write=True) as s:
        s.add_all(
            [
                MassRow(id=1, name="a", active=True),
                MassRow(id=2, name="b", active=False),
                MassRow(id=3, name="c", active=False),
            ]
        )


async def test_mass_update_returns_rowcount(configured_db):
    await _seed()
    n = await QuerySet(MassRow).filter(active=False).update(name="archived")
    assert n == 2
    rows = await QuerySet(MassRow).filter(name="archived").all()
    assert {r.id for r in rows} == {2, 3}


async def test_mass_delete_returns_rowcount(configured_db):
    await _seed()
    n = await QuerySet(MassRow).filter(active=False).delete()
    assert n == 2
    assert await QuerySet(MassRow).count() == 1


async def test_unfiltered_update_raises(configured_db):
    with pytest.raises(QueryError, match="filter"):
        await QuerySet(MassRow).update(name="wiped")


async def test_unfiltered_delete_raises(configured_db):
    with pytest.raises(QueryError, match="filter"):
        await QuerySet(MassRow).delete()


async def test_update_all_updates_every_row(configured_db):
    await _seed()
    n = await QuerySet(MassRow).update_all(name="all")
    assert n == 3
    rows = await QuerySet(MassRow).all()
    assert all(r.name == "all" for r in rows)


async def test_delete_all_deletes_every_row(configured_db):
    await _seed()
    n = await QuerySet(MassRow).delete_all()
    assert n == 3
    assert await QuerySet(MassRow).count() == 0


async def test_repository_update_all_and_delete_all(configured_db):
    from alchemiq.repository import Repository

    await _seed()
    repo = Repository(MassRow)
    assert await repo.update_all(active=True) == 3
    assert await repo.count(active=True) == 3
    assert await repo.delete_all() == 3
    assert await repo.count() == 0
