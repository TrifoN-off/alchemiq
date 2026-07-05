import pytest
from sqlalchemy.dialects import postgresql

from alchemiq import Model
from alchemiq.query import QuerySet
from alchemiq.types import PK


class SliceRow(Model):
    id: PK[int]
    name: str


def sql(qs) -> str:
    return str(
        qs.compile().compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def test_slice_sets_offset_and_limit():
    out = sql(QuerySet(SliceRow)[20:30])
    assert "LIMIT 10" in out
    assert "OFFSET 20" in out


def test_slice_start_only():
    out = sql(QuerySet(SliceRow)[5:])
    assert "OFFSET 5" in out


def test_int_index_rejected():
    with pytest.raises(TypeError):
        QuerySet(SliceRow)[0]


def test_step_rejected():
    with pytest.raises(ValueError):
        QuerySet(SliceRow)[0:10:2]
