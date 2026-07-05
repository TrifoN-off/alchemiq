from __future__ import annotations

import pytest

from alchemiq.migrations.clickhouse.operations import (
    AddColumn,
    Column,
    DropColumn,
)
from alchemiq.migrations.clickhouse.render import render_migration_source

pytestmark = pytest.mark.unit


def test_render_source_with_inverse_and_stubs() -> None:
    up = [AddColumn("events", Column("country", "LowCardinality(String)"))]
    down = [DropColumn("events", "country")]
    src = render_migration_source(
        revision="0003",
        down_revision="0002",
        class_name="Migration0003",
        up_ops=up,
        down_ops=down,
        unsafe_stubs=['op.drop_column("events", "legacy")'],
    )
    assert "class Migration0003(Migration):" in src
    assert 'revision = "0003"' in src
    assert 'down_revision = "0002"' in src
    assert 'op.add_column("events", op.Column("country", "LowCardinality(String)"))' in src
    assert "# --- MANUAL: unsafe operations" in src
    assert '# op.drop_column("events", "legacy")' in src
    # The rendered module must be valid Python.
    compile(src, "<rendered>", "exec")


def test_render_empty_up_uses_pass() -> None:
    src = render_migration_source(
        revision="0001", down_revision=None, class_name="M", up_ops=[], down_ops=[], unsafe_stubs=[]
    )
    assert "        pass" in src
    compile(src, "<rendered>", "exec")
