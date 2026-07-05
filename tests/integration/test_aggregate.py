from __future__ import annotations

import pytest

from alchemiq import Avg, Count, Max, Min, Model, Repository, Sum
from alchemiq.runtime.session import session_scope
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class AggRow(Model):
    __tablename__ = "agg_row"
    id: PK[int]
    name: str
    amount: int


async def _seed() -> None:
    async with session_scope(write=True) as s:
        s.add_all(
            [
                AggRow(id=1, name="a", amount=10),
                AggRow(id=2, name="a", amount=20),
                AggRow(id=3, name="b", amount=30),
            ]
        )


async def test_aggregate_basic(configured_db) -> None:
    await _seed()
    result = await Repository(AggRow).aggregate(
        total=Sum("amount"), n=Count(), hi=Max("amount"), lo=Min("amount")
    )
    assert result == {"total": 60, "n": 3, "hi": 30, "lo": 10}


async def test_aggregate_with_filter(configured_db) -> None:
    await _seed()
    result = await Repository(AggRow).filter(name="a").aggregate(total=Sum("amount"), n=Count())
    assert result == {"total": 30, "n": 2}


async def test_aggregate_avg(configured_db) -> None:
    await _seed()
    result = await Repository(AggRow).aggregate(avg=Avg("amount"))
    assert float(result["avg"]) == pytest.approx(20.0)


async def test_count_distinct(configured_db) -> None:
    await _seed()
    result = await Repository(AggRow).aggregate(names=Count("name", distinct=True))
    assert result == {"names": 2}


async def test_aggregate_empty_set(configured_db) -> None:
    result = (
        await Repository(AggRow).filter(name="missing").aggregate(total=Sum("amount"), n=Count())
    )
    assert result == {"total": None, "n": 0}


async def test_count_named_field(configured_db) -> None:
    await _seed()
    result = await Repository(AggRow).aggregate(n=Count("id"))
    assert result == {"n": 3}


async def test_aggregate_no_exprs_raises(configured_db) -> None:
    with pytest.raises(ValueError):
        await Repository(AggRow).aggregate()
