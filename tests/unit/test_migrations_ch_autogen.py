from __future__ import annotations

from datetime import datetime

import pytest

from alchemiq.clickhouse.engines import MergeTree, ReplacingMergeTree
from alchemiq.clickhouse.model import ClickHouseModel
from alchemiq.clickhouse.types import DateTime64, LowCardinality, UInt8, UInt64
from alchemiq.migrations.clickhouse import autogen

pytestmark = pytest.mark.unit


class _AgEvents(ClickHouseModel):
    id: int = UInt64()
    country: str = LowCardinality(str)

    class Meta:
        table_name = "autogen_events"
        engine = MergeTree(order_by=("id",))


def test_diff_new_table_emits_create() -> None:
    safe, unsafe = autogen.diff(live_tables=set(), live_columns_by_table={}, live_engines={})
    created = [o for o in safe if getattr(o, "name", None) == "autogen_events"]
    assert created and type(created[0]).__name__ == "CreateTable"
    assert not [u for u in unsafe if "autogen_events" in u.detail]


def test_diff_missing_column_emits_add() -> None:
    safe, unsafe = autogen.diff(
        live_tables={"autogen_events"},
        live_columns_by_table={"autogen_events": {"id": "UInt64"}},
        live_engines={"autogen_events": "MergeTree"},
    )
    adds = [o for o in safe if type(o).__name__ == "AddColumn"]
    assert any(o.column.name == "country" for o in adds)


def test_diff_dropped_column_is_unsafe() -> None:
    _, unsafe = autogen.diff(
        live_tables={"autogen_events"},
        live_columns_by_table={
            "autogen_events": {
                "id": "UInt64",
                "country": "LowCardinality(String)",
                "legacy": "String",
            }
        },
        live_engines={"autogen_events": "MergeTree"},
    )
    assert any(u.kind == "drop column" and "legacy" in u.detail for u in unsafe)


class _AgRepl(ClickHouseModel):
    id: int = UInt64()
    country: str = LowCardinality(str)
    _version: datetime = DateTime64(3)
    _is_deleted: int = UInt8(default=0)

    class Meta:
        table_name = "autogen_repl"
        engine = ReplacingMergeTree(order_by=("id",), version="_version", is_deleted="_is_deleted")


def test_replacing_merge_tree_no_false_positive_engine_change() -> None:
    """Parameterised engine name must not generate a spurious 'change engine' Unsafe."""
    safe, unsafe = autogen.diff(
        live_tables={"autogen_repl"},
        live_columns_by_table={
            "autogen_repl": {
                "id": "UInt64",
                "country": "LowCardinality(String)",
            }
        },
        live_engines={"autogen_repl": "ReplacingMergeTree"},
    )
    engine_unsafes = [u for u in unsafe if u.kind == "change engine" and "autogen_repl" in u.detail]
    assert not engine_unsafes, engine_unsafes


def test_inverse_of_create_and_add() -> None:
    from alchemiq.migrations.clickhouse.operations import AddColumn, Column, CreateTable

    assert (
        type(autogen.inverse(CreateTable("t", (), "ENGINE = MergeTree ORDER BY id"))).__name__
        == "DropTable"
    )
    inv = autogen.inverse(AddColumn("t", Column("c", "String")))
    assert type(inv).__name__ == "DropColumn" and inv.name == "c"


def test_diff_change_type_is_unsafe() -> None:
    _, unsafe = autogen.diff(
        live_tables={"autogen_events"},
        live_columns_by_table={
            "autogen_events": {"id": "String", "country": "LowCardinality(String)"}
        },
        live_engines={"autogen_events": "MergeTree"},
    )
    assert any(u.kind == "change type" and "id" in u.detail for u in unsafe)


def test_diff_change_engine_is_unsafe() -> None:
    _, unsafe = autogen.diff(
        live_tables={"autogen_events"},
        live_columns_by_table={
            "autogen_events": {"id": "UInt64", "country": "LowCardinality(String)"}
        },
        live_engines={"autogen_events": "ReplacingMergeTree"},
    )
    assert any(u.kind == "change engine" and "autogen_events" in u.detail for u in unsafe)


def test_diff_drop_table_is_unsafe() -> None:
    """A table in the DB that is NOT in any ClickHouseModel should appear as 'drop table' unsafe."""
    _, unsafe = autogen.diff(
        live_tables={"autogen_events", "orphan_table"},
        live_columns_by_table={
            "autogen_events": {"id": "UInt64", "country": "LowCardinality(String)"},
            "orphan_table": {"x": "String"},
        },
        live_engines={"autogen_events": "MergeTree", "orphan_table": "MergeTree"},
    )
    assert any(u.kind == "drop table" and "orphan_table" in u.detail for u in unsafe)


def test_inverse_unknown_op_raises() -> None:
    import pytest

    from alchemiq.migrations.clickhouse.operations import DropTable

    with pytest.raises(ValueError, match="no automatic inverse"):
        autogen.inverse(DropTable("t"))
