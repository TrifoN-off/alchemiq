import pytest

from alchemiq import Model, Repository, UnitOfWork
from alchemiq.exceptions import NotFoundError
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class WrRow(Model):
    __tablename__ = "repo_write_wr_row"
    id: PK[int]
    name: str
    age: int


async def test_create_assigns_and_persists(configured_db):
    repo = Repository(WrRow)
    obj = await repo.create(id=1, name="ann", age=30)
    assert obj.id == 1
    assert (await repo.get(id=1)).name == "ann"


async def test_add_constructed_instance(configured_db):
    repo = Repository(WrRow)
    obj = await repo.add(WrRow(id=2, name="bob", age=40))
    assert (await repo.get(id=2)).age == 40
    assert obj.id == 2


async def test_update_changes_fields(configured_db):
    repo = Repository(WrRow)
    await repo.create(id=3, name="cara", age=25)
    updated = await repo.update(3, age=26)
    assert updated.age == 26
    assert (await repo.get(id=3)).age == 26


async def test_update_missing_raises(configured_db):
    with pytest.raises(NotFoundError):
        await Repository(WrRow).update(999, age=1)


async def test_delete(configured_db):
    repo = Repository(WrRow)
    await repo.create(id=4, name="dan", age=50)
    await repo.delete(4)
    assert await repo.get_or_none(id=4) is None


async def test_bulk_create_and_update(configured_db):
    repo = Repository(WrRow)
    async with UnitOfWork():
        await repo.bulk_create([WrRow(id=10, name="x", age=1), WrRow(id=11, name="y", age=2)])
    rows = sorted(await repo.all(), key=lambda r: r.id)
    for r in rows:
        r.age = 100
    n = await repo.bulk_update(rows, fields=["age"])
    assert n == len(rows)
    assert all(r.age == 100 for r in await repo.all())
