from pathlib import Path

import pytest

from alchemiq.clickhouse.connection import get_clickhouse_client
from alchemiq.migrations.clickhouse import history, runner
from alchemiq.migrations.config import AlchemiqConfig

pytestmark = pytest.mark.clickhouse

_MIG_0001 = """
from alchemiq.migrations import Migration

class Init(Migration):
    revision = "0001"
    down_revision = None

    def up(self, op):
        op.create_table(
            "mig_runner_t",
            [op.Column("id", "UInt64"), op.Column("name", "String")],
            "ENGINE = MergeTree ORDER BY id",
        )

    def down(self, op):
        op.drop_table("mig_runner_t")
"""

_MIG_0002 = """
from alchemiq.migrations import Migration

class AddCol(Migration):
    revision = "0002"
    down_revision = "0001"

    def up(self, op):
        op.add_column("mig_runner_t", op.Column("country", "LowCardinality(String)"))

    def down(self, op):
        op.drop_column("mig_runner_t", "country")
"""


def _project(tmp_path: Path) -> AlchemiqConfig:
    ch = tmp_path / "migrations" / "clickhouse"
    ch.mkdir(parents=True)
    (ch / "0001_init.py").write_text(_MIG_0001, "utf-8")
    (ch / "0002_add_col.py").write_text(_MIG_0002, "utf-8")
    return AlchemiqConfig(root=tmp_path, models=(), migrations_dir="migrations")


async def _columns(table: str) -> set[str]:
    client = await get_clickhouse_client()
    res = await client.query(f"SELECT name FROM system.columns WHERE table = '{table}'")
    return {r[0] for r in res.result_rows}


async def test_migrate_apply_rollback_history(configured_clickhouse, tmp_path) -> None:
    cfg = _project(tmp_path)
    client = await get_clickhouse_client()
    try:
        await runner.migrate(cfg)
        assert await _columns("mig_runner_t") == {"id", "name", "country"}
        assert await history.applied_revisions(client) == {"0001", "0002"}

        sql = await runner.showsql(cfg)
        assert sql == []  # all applied => nothing pending

        await runner.rollback(cfg)  # undo 0002
        assert "country" not in await _columns("mig_runner_t")
        assert await history.applied_revisions(client) == {"0001"}
    finally:
        await client.command("DROP TABLE IF EXISTS mig_runner_t")
        await client.command(f"DROP TABLE IF EXISTS {history.HISTORY_TABLE}")


async def test_showsql_lists_pending(configured_clickhouse, tmp_path) -> None:
    cfg = _project(tmp_path)
    client = await get_clickhouse_client()
    try:
        await history.ensure_history(client)
        sql = await runner.showsql(cfg)
        assert any(s.startswith("CREATE TABLE IF NOT EXISTS mig_runner_t") for s in sql)
        assert any("ADD COLUMN IF NOT EXISTS country" in s for s in sql)
    finally:
        await client.command(f"DROP TABLE IF EXISTS {history.HISTORY_TABLE}")


async def test_makemigrations_autogen_then_migrate(configured_clickhouse, tmp_path) -> None:
    from alchemiq.clickhouse.engines import MergeTree
    from alchemiq.clickhouse.model import ClickHouseModel
    from alchemiq.clickhouse.types import UInt64
    from alchemiq.migrations.clickhouse.history import HISTORY_TABLE
    from alchemiq.migrations.config import AlchemiqConfig, ClickHouseSettings

    class _AutoT(ClickHouseModel):
        id: int = UInt64()

        class Meta:
            table_name = "mig_auto_t"
            engine = MergeTree(order_by=("id",))

    client = await get_clickhouse_client()
    await client.command("DROP TABLE IF EXISTS mig_auto_t")
    cfg = AlchemiqConfig(
        root=tmp_path,
        models=(),
        migrations_dir="migrations",
        clickhouse=ClickHouseSettings(host="x", database="test", username="u", password="p"),
    )
    try:
        await runner.makemigrations(cfg, "auto")
        files = list((tmp_path / "migrations" / "clickhouse").glob("*.py"))
        assert files, "a migration file should have been generated"
        await runner.migrate(cfg)
        res = await client.query("EXISTS TABLE mig_auto_t")
        assert res.result_rows[0][0] == 1
    finally:
        await client.command("DROP TABLE IF EXISTS mig_auto_t")
        await client.command(f"DROP TABLE IF EXISTS {HISTORY_TABLE}")
