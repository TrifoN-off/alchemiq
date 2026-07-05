import pytest

from alchemiq.clickhouse import ClickHouseModel, MergeTree
from alchemiq.clickhouse.connection import get_clickhouse_client
from alchemiq.clickhouse.query import ClickHouseQuerySet
from alchemiq.clickhouse.types import UInt32


class _Visit(ClickHouseModel):
    user_id: int = UInt32()
    country: str

    class Meta:
        engine = MergeTree(order_by=("user_id",))


async def _seed():
    client = await get_clickhouse_client()
    await client.insert(
        "_visit",
        [[1, "US"], [2, "US"], [3, "DE"]],
        column_names=["user_id", "country"],
    )


@pytest.mark.clickhouse
async def test_all_returns_model_instances(configured_clickhouse):
    await _seed()
    rows = await ClickHouseQuerySet(_Visit).order_by("user_id").all()
    assert [r.user_id for r in rows] == [1, 2, 3]
    assert all(isinstance(r, _Visit) for r in rows)


@pytest.mark.clickhouse
async def test_filter_count_exists_first(configured_clickhouse):
    await _seed()
    qs = ClickHouseQuerySet(_Visit).filter(country="US")
    assert await qs.count() == 2
    assert await qs.exists() is True
    assert (await qs.order_by("user_id").first()).user_id == 1
    assert await ClickHouseQuerySet(_Visit).filter(country="FR").exists() is False


@pytest.mark.clickhouse
async def test_iterate_batches(configured_clickhouse):
    await _seed()
    seen = []
    async for block in ClickHouseQuerySet(_Visit).order_by("user_id").iterate(batch_size=2):
        seen.append([r.user_id for r in block])
    flat = [x for b in seen for x in b]
    assert sorted(flat) == [1, 2, 3]


@pytest.mark.clickhouse
async def test_get_or_none_single(configured_clickhouse):
    await _seed()
    row = await ClickHouseQuerySet(_Visit).get_or_none(country="DE")
    assert row is not None and row.user_id == 3


@pytest.mark.clickhouse
async def test_get_or_none_missing_returns_none(configured_clickhouse):
    await _seed()
    assert await ClickHouseQuerySet(_Visit).get_or_none(country="FR") is None


@pytest.mark.clickhouse
async def test_get_or_none_multiple_raises(configured_clickhouse):
    await _seed()
    from alchemiq.exceptions import MultipleResultsFound

    with pytest.raises(MultipleResultsFound):
        await ClickHouseQuerySet(_Visit).get_or_none(country="US")
