"""DDL compilation of alchemiq column types on sqlite vs postgresql."""

from __future__ import annotations

from sqlalchemy.dialects import postgresql, sqlite

from alchemiq.types import JSON, PK, UUID4, UUID7, DateTimeTz


def test_pg_ddl_is_unchanged() -> None:
    pg = postgresql.dialect()
    assert str(PK().column_type().compile(dialect=pg)) == "BIGINT"
    assert str(UUID4().column_type().compile(dialect=pg)) == "UUID"
    assert str(UUID7().column_type().compile(dialect=pg)) == "UUID"
    assert str(JSON().column_type().compile(dialect=pg)) == "JSONB"
    assert "TIMESTAMP WITH TIME ZONE" in str(DateTimeTz().column_type().compile(dialect=pg))


def test_sqlite_variants_compile() -> None:
    sq = sqlite.dialect()
    assert str(PK().column_type().compile(dialect=sq)) == "INTEGER"
    assert str(UUID4().column_type().compile(dialect=sq)) == "CHAR(32)"
    assert str(UUID7().column_type().compile(dialect=sq)) == "CHAR(32)"
    assert str(JSON().column_type().compile(dialect=sq)) == "JSON"
    assert "DATETIME" in str(DateTimeTz().column_type().compile(dialect=sq))
