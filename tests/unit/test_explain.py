from __future__ import annotations

import pytest
from sqlalchemy.dialects import postgresql

from alchemiq import Model
from alchemiq.query.explain import _Explain
from alchemiq.query.queryset import QuerySet
from alchemiq.types import PK

pytestmark = pytest.mark.unit


class _ExplainRow(Model):
    __tablename__ = "explain_unit_explain"
    id: PK[int]
    name: str


def _sql(*, analyze: bool, fmt: str) -> str:
    qs = QuerySet(_ExplainRow).filter(name="x").limit(5)
    stmt = _Explain(qs.compile(), analyze=analyze, fmt=fmt)
    return str(stmt.compile(dialect=postgresql.dialect()))


def test_explain_text_prefix() -> None:
    assert _sql(analyze=False, fmt="text").startswith("EXPLAIN SELECT")


def test_explain_analyze_prefix() -> None:
    assert _sql(analyze=True, fmt="text").startswith("EXPLAIN (ANALYZE) SELECT")


def test_explain_json_prefix() -> None:
    assert _sql(analyze=False, fmt="json").startswith("EXPLAIN (FORMAT JSON) SELECT")


def test_explain_analyze_json_prefix() -> None:
    assert _sql(analyze=True, fmt="json").startswith("EXPLAIN (ANALYZE, FORMAT JSON) SELECT")
