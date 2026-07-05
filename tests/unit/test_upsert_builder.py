from __future__ import annotations

import pytest
from sqlalchemy.dialects import postgresql

from alchemiq import Model
from alchemiq.exceptions import ConfigError
from alchemiq.repository.upsert import build_upsert
from alchemiq.types import PK

pytestmark = pytest.mark.unit


class UpsertUnitRow(Model):
    __tablename__ = "upsert_unit_row"
    id: PK[int]
    email: str
    name: str


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect())).lower()


def test_default_conflict_is_pk_do_update() -> None:
    objs = [UpsertUnitRow(id=1, email="a@b.c", name="A")]
    sql = _sql(
        build_upsert(UpsertUnitRow, objs, conflict=None, update_fields=None, ignore_conflicts=False)
    )
    assert "on conflict (id) do update" in sql
    assert "email" in sql and "name" in sql


def test_ignore_conflicts_do_nothing() -> None:
    objs = [UpsertUnitRow(id=1, email="a@b.c", name="A")]
    sql = _sql(
        build_upsert(UpsertUnitRow, objs, conflict=None, update_fields=None, ignore_conflicts=True)
    )
    assert "do nothing" in sql


def test_explicit_conflict_and_update_fields() -> None:
    objs = [UpsertUnitRow(id=1, email="a@b.c", name="A")]
    stmt = build_upsert(
        UpsertUnitRow, objs, conflict=["email"], update_fields=["name"], ignore_conflicts=False
    )
    sql = _sql(stmt)
    assert "on conflict (email) do update" in sql
    assert "set name" in sql.replace('"', "")


def test_unknown_conflict_column_raises() -> None:
    objs = [UpsertUnitRow(id=1, email="a@b.c", name="A")]
    with pytest.raises(ConfigError):
        build_upsert(
            UpsertUnitRow, objs, conflict=["nope"], update_fields=None, ignore_conflicts=False
        )


def test_heterogeneous_rows_raise() -> None:
    a = UpsertUnitRow(id=1, email="a@b.c", name="A")
    b = UpsertUnitRow(id=2, email="b@b.c", name="B")
    b.__dict__.pop("name", None)  # simulate an instance that didn't populate `name`
    with pytest.raises(ConfigError):
        build_upsert(
            UpsertUnitRow, [a, b], conflict=None, update_fields=None, ignore_conflicts=False
        )
