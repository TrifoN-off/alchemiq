import pytest

from alchemiq.clickhouse import ClickHouseModel, ClickHouseRepository, MergeTree
from alchemiq.clickhouse.types import UInt32


class _Ev(ClickHouseModel):
    id: int = UInt32()
    name: str

    class Meta:
        engine = MergeTree(order_by=("id",))


@pytest.mark.clickhouse
async def test_insert_and_bulk_insert(configured_clickhouse):
    repo = ClickHouseRepository(_Ev)
    await repo.insert(_Ev(id=1, name="a"))
    await repo.bulk_insert([_Ev(id=2, name="b"), _Ev(id=3, name="c")])
    rows = await repo.order_by("id").all()
    assert [(r.id, r.name) for r in rows] == [(1, "a"), (2, "b"), (3, "c")]
