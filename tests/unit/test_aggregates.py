from __future__ import annotations

import pytest

from alchemiq import Model
from alchemiq.exceptions import QueryError
from alchemiq.query.aggregates import Avg, Count, Max, Min, Sum
from alchemiq.types import PK

pytestmark = pytest.mark.unit


class AggUnitRow(Model):
    __tablename__ = "agg_unit_row"
    id: PK[int]
    name: str
    amount: int


def test_count_star_resolves_to_count() -> None:
    sql = str(Count().resolve(AggUnitRow))
    assert "count(" in sql.lower()


def test_sum_resolves_to_sum_of_column() -> None:
    sql = str(Sum("amount").resolve(AggUnitRow)).lower()
    assert "sum(" in sql and "amount" in sql


def test_count_distinct_renders_distinct() -> None:
    sql = str(Count("amount", distinct=True).resolve(AggUnitRow)).lower()
    assert "distinct" in sql


def test_each_func_resolves() -> None:
    for expr in (Avg("amount"), Min("amount"), Max("amount")):
        assert expr.resolve(AggUnitRow) is not None


def test_traversal_field_raises() -> None:
    with pytest.raises(QueryError):
        Sum("author__age").resolve(AggUnitRow)


def test_unknown_field_raises() -> None:
    with pytest.raises(QueryError):
        Sum("nope").resolve(AggUnitRow)
