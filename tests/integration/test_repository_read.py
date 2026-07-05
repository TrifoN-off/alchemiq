import pytest

from alchemiq import Model, Repository
from alchemiq.runtime.session import session_scope
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class RdRow(Model):
    __tablename__ = "repo_read_rd_row"
    id: PK[int]
    name: str
    age: int


async def _seed():
    async with session_scope(write=True) as s:
        s.add_all([RdRow(id=i, name=f"n{i}", age=10 + i) for i in range(1, 4)])


async def test_read_methods(configured_db):
    await _seed()
    repo = Repository(RdRow)
    assert (await repo.get(id=1)).name == "n1"
    assert await repo.get_or_none(id=99) is None
    assert await repo.count() == 3
    assert await repo.exists(age__gte=12) is True
    assert {r.id for r in await repo.all()} == {1, 2, 3}
    assert (await repo.order_by("age").first()).id == 1
    assert (await repo.last()).id == 3
