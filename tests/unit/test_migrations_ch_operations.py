import pytest

from alchemiq.migrations.clickhouse.operations import (
    AddColumn,
    Column,
    CreateTable,
    DropColumn,
    DropTable,
    Operation,
    Operations,
    RawSQL,
)

pytestmark = pytest.mark.unit


def test_column_render() -> None:
    assert Column("id", "UInt64").render() == "id UInt64"
    assert Column("c", "String", default="''").render() == "c String DEFAULT ''"


def test_create_table_to_sql() -> None:
    op = CreateTable(
        "events",
        (Column("id", "UInt64"), Column("ts", "DateTime64(3)")),
        "ENGINE = MergeTree ORDER BY id",
    )
    assert op.to_sql() == (
        "CREATE TABLE IF NOT EXISTS events (\n"
        "  id UInt64,\n"
        "  ts DateTime64(3)\n"
        ") ENGINE = MergeTree ORDER BY id"
    )


def test_alter_ops_to_sql() -> None:
    assert AddColumn("events", Column("country", "LowCardinality(String)")).to_sql() == (
        "ALTER TABLE events ADD COLUMN IF NOT EXISTS country LowCardinality(String)"
    )
    assert DropColumn("events", "legacy").to_sql() == (
        "ALTER TABLE events DROP COLUMN IF EXISTS legacy"
    )
    assert DropTable("events").to_sql() == "DROP TABLE IF EXISTS events"
    assert RawSQL("OPTIMIZE TABLE x FINAL").to_sql() == "OPTIMIZE TABLE x FINAL"


def test_render_call_roundtrips_to_python_source() -> None:
    assert AddColumn("events", Column("country", "LowCardinality(String)")).render_call() == (
        'op.add_column("events", op.Column("country", "LowCardinality(String)"))'
    )
    assert DropTable("events").render_call() == 'op.drop_table("events")'


def test_recorder_collects_operations() -> None:
    op = Operations()
    op.create_table("t", [op.Column("id", "UInt64")], "ENGINE = MergeTree ORDER BY id")
    op.add_column("t", op.Column("name", "String"))
    op.execute("OPTIMIZE TABLE t FINAL")
    assert [type(o).__name__ for o in op.operations] == ["CreateTable", "AddColumn", "RawSQL"]
    assert op.operations[0].to_sql().startswith("CREATE TABLE IF NOT EXISTS t (")


def test_column_render_with_codec() -> None:
    assert Column("data", "String", codec="ZSTD").render() == "data String CODEC(ZSTD)"


def test_column_render_call_with_default_and_codec() -> None:
    col = Column("ts", "DateTime64(3)", default="now64(3)", codec="Delta")
    rc = col.render_call()
    assert 'default="now64(3)"' in rc
    assert 'codec="Delta"' in rc


def test_operation_base_abstract_methods_raise() -> None:
    import pytest

    op = Operation()
    with pytest.raises(NotImplementedError):
        op.to_sql()
    with pytest.raises(NotImplementedError):
        op.render_call()


def test_create_table_render_call() -> None:
    ct = CreateTable("events", (Column("id", "UInt64"),), "ENGINE = MergeTree ORDER BY id")
    rc = ct.render_call()
    assert rc.startswith('op.create_table("events"')
    assert '"UInt64"' in rc
    assert '"ENGINE = MergeTree ORDER BY id"' in rc


def test_raw_sql_render_call() -> None:
    r = RawSQL("OPTIMIZE TABLE x FINAL")
    assert r.render_call() == 'op.execute("OPTIMIZE TABLE x FINAL")'


def test_recorder_drop_column_and_drop_table() -> None:
    op = Operations()
    op.drop_column("events", "legacy")
    op.drop_table("events")
    assert [type(o).__name__ for o in op.operations] == ["DropColumn", "DropTable"]
    assert op.operations[0].to_sql() == "ALTER TABLE events DROP COLUMN IF EXISTS legacy"
    assert op.operations[1].to_sql() == "DROP TABLE IF EXISTS events"
