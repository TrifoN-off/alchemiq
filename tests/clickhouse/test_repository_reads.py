import pytest

from alchemiq.clickhouse import ClickHouseModel, ClickHouseRepository, MergeTree
from alchemiq.clickhouse.connection import get_clickhouse_client
from alchemiq.clickhouse.types import UInt32


class _Sale(ClickHouseModel):
    id: int = UInt32()
    region: str
    amount: int = UInt32()

    class Meta:
        engine = MergeTree(order_by=("id",))


class _SaleRepo(ClickHouseRepository[_Sale]):
    pass


async def _seed():
    client = await get_clickhouse_client()
    await client.insert(
        "_sale",
        [[1, "EU", 10], [2, "EU", 20], [3, "US", 30]],
        column_names=["id", "region", "amount"],
    )


@pytest.mark.clickhouse
async def test_repo_filter_all_count(configured_clickhouse):
    await _seed()
    repo = _SaleRepo()
    rows = await repo.filter(region="EU").order_by("id").all()
    assert [r.id for r in rows] == [1, 2]
    assert await repo.filter(region="EU").count() == 2


@pytest.mark.clickhouse
async def test_repo_raw_aggregation(configured_clickhouse):
    await _seed()
    repo = _SaleRepo()
    sql = "SELECT region, sum(amount) AS total FROM _sale GROUP BY region ORDER BY region"
    rows = await repo.raw(sql)
    assert rows == [{"region": "EU", "total": 30}, {"region": "US", "total": 30}]


@pytest.mark.clickhouse
async def test_repo_exists_with_filter_args(configured_clickhouse):
    """Lines 141-142: repo.exists(*args, **lookups) triggers the filter branch."""
    await _seed()
    repo = _SaleRepo()
    assert await repo.exists(region="EU") is True
    assert await repo.exists(region="NOWHERE") is False


@pytest.mark.clickhouse
async def test_repo_get_or_none_delegate(configured_clickhouse):
    """Line 145: repo.get_or_none() returns matching row or None."""
    await _seed()
    repo = _SaleRepo()
    row = await repo.get_or_none(id=1)
    assert row is not None and row.id == 1
    assert await repo.get_or_none(id=999) is None


@pytest.mark.clickhouse
async def test_repo_iterate_yields_rows(configured_clickhouse):
    """Line 148: repo.iterate() streams rows in batches."""
    await _seed()
    repo = _SaleRepo()
    collected = []
    async for batch in repo.iterate(batch_size=2):
        collected.extend(batch)
    assert len(collected) == 3


@pytest.mark.clickhouse
async def test_repo_raw_as_model_returns_instances(configured_clickhouse):
    """Line 161: repo.raw(sql, as_model=True) returns model instances."""
    await _seed()
    repo = _SaleRepo()
    sql = "SELECT id, region, amount FROM _sale WHERE id = 1"
    rows = await repo.raw(sql, as_model=True)
    assert len(rows) == 1
    assert isinstance(rows[0], _Sale)
    assert rows[0].id == 1


@pytest.mark.clickhouse
async def test_repo_all_direct(configured_clickhouse):
    """Lines 131-132: repo.all() called directly (not via chained QuerySet)."""
    await _seed()
    repo = _SaleRepo()
    rows = await repo.all()
    assert len(rows) == 3


@pytest.mark.clickhouse
async def test_repo_first_direct(configured_clickhouse):
    """Lines 133-134: repo.first() called directly returns one row or None."""
    await _seed()
    repo = _SaleRepo()
    row = await repo.first()
    assert row is not None
