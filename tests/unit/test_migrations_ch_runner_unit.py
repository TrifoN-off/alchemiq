from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alchemiq.migrations.clickhouse import runner
from alchemiq.migrations.clickhouse.migration import Migration
from alchemiq.migrations.clickhouse.operations import Operations
from alchemiq.migrations.config import AlchemiqConfig, ClickHouseSettings

pytestmark = pytest.mark.unit

_GET_CLIENT = "alchemiq.clickhouse.connection.get_clickhouse_client"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(tmp_path: Path) -> AlchemiqConfig:
    return AlchemiqConfig(
        root=tmp_path,
        models=(),
        clickhouse=ClickHouseSettings("h", "d", "u", "p"),
    )


def _mock_client(applied: set[str] | None = None) -> MagicMock:
    client = MagicMock()
    client.command = AsyncMock()
    result = MagicMock()
    result.result_rows = [(r,) for r in (applied or set())]
    client.query = AsyncMock(return_value=result)
    client.insert = AsyncMock()
    return client


def _write_migration(ch_dir: Path, revision: str, down_revision: str | None = None) -> None:
    """Write a minimal valid migration file into ch_dir."""
    dr = "None" if down_revision is None else f'"{down_revision}"'
    source = textwrap.dedent(f"""\
        from alchemiq.migrations import Migration
        from alchemiq.migrations.clickhouse.operations import Operations

        class Mig{revision}(Migration):
            revision = "{revision}"
            down_revision = {dr}

            def up(self, op: Operations) -> None:
                op.execute("SELECT 1")

            def down(self, op: Operations) -> None:
                op.execute("SELECT 0")
    """)
    ch_dir.mkdir(parents=True, exist_ok=True)
    (ch_dir / f"{revision}_test.py").write_text(source, "utf-8")


# ---------------------------------------------------------------------------
# Pure helpers (no CH client)
# ---------------------------------------------------------------------------


def test_slugify_strips_path_traversal_and_separators() -> None:
    from alchemiq.migrations.clickhouse.runner import _slugify

    assert _slugify("../../etc/passwd") == "etcpasswd"
    assert _slugify("add users") == "add_users"
    assert _slugify("Add Users/Table") == "add_userstable"
    assert _slugify(None) == "auto"
    assert _slugify("") == "auto"
    assert _slugify("!@#$%") == "auto"
    # the generated filename can never escape the dir
    assert "/" not in _slugify("a/b/c") and ".." not in _slugify("..")


def test_ch_dir_creates_directory(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    d = runner._ch_dir(cfg)
    assert d.is_dir()
    assert d == tmp_path / "migrations" / "clickhouse"


def test_next_revision_first(tmp_path: Path) -> None:
    d = tmp_path / "migrations" / "clickhouse"
    d.mkdir(parents=True)
    rev, down = runner._next_revision(d)
    assert rev == "0001"
    assert down is None


def test_next_revision_increments(tmp_path: Path) -> None:
    d = tmp_path / "migrations" / "clickhouse"
    d.mkdir(parents=True)
    (d / "0001_init.py").write_text("", "utf-8")
    (d / "0002_add.py").write_text("", "utf-8")
    rev, down = runner._next_revision(d)
    assert rev == "0003"
    assert down == "0002"


def test_stub_for_drop_column() -> None:
    from alchemiq.migrations.clickhouse.autogen import Unsafe

    u = Unsafe("drop column", "events.legacy  (in DB, not in model)")
    stub = runner._stub_for(u)
    assert "drop_column" in stub
    assert '"events"' in stub
    assert '"legacy"' in stub


def test_stub_for_change_type() -> None:
    from alchemiq.migrations.clickhouse.autogen import Unsafe

    u = Unsafe("change type", "events.id  UInt32 -> UInt64")
    stub = runner._stub_for(u)
    assert "MODIFY COLUMN" in stub


def test_stub_for_other_kind() -> None:
    from alchemiq.migrations.clickhouse.autogen import Unsafe

    u = Unsafe("change engine", "events  MergeTree -> ReplacingMergeTree")
    stub = runner._stub_for(u)
    assert "change engine" in stub


def test_load_migrations_returns_sorted(tmp_path: Path) -> None:
    d = tmp_path / "ch"
    _write_migration(d, "0002")
    _write_migration(d, "0001")
    migrations = runner.load_migrations(d)
    assert [m.revision for m in migrations] == ["0001", "0002"]


def test_load_migrations_empty_dir(tmp_path: Path) -> None:
    d = tmp_path / "ch"
    d.mkdir()
    assert runner.load_migrations(d) == []


def test_find_migration_raises_when_no_subclass(tmp_path: Path) -> None:
    module = MagicMock()
    module.__name__ = "empty"
    del module.__dict__
    # Use a real module-like object that has no Migration subclass
    import types

    mod = types.ModuleType("empty")
    with pytest.raises(LookupError, match="no Migration subclass"):
        runner._find_migration(mod)


def test_ops_calls_migration_direction(tmp_path: Path) -> None:
    """_ops collects operations from migration.up/down."""

    class _M(Migration):
        revision = "0001"

        def up(self, op: Operations) -> None:
            op.execute("SELECT 1")

        def down(self, op: Operations) -> None:
            op.execute("SELECT 0")

    ops = runner._ops(_M(), "up")
    assert len(ops) == 1
    assert ops[0].to_sql() == "SELECT 1"

    ops_down = runner._ops(_M(), "down")
    assert ops_down[0].to_sql() == "SELECT 0"


# ---------------------------------------------------------------------------
# Async runner functions (mocked CH client)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migrate_applies_pending(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    d = runner._ch_dir(cfg)
    _write_migration(d, "0001")

    client = _mock_client(applied=set())
    with patch(_GET_CLIENT, AsyncMock(return_value=client)):
        await runner.migrate(cfg)

    # Should have called ensure_history + applied_revisions + command for SELECT 1 + record_applied
    assert client.command.await_count >= 2  # CREATE TABLE + SELECT 1
    # record_applied uses client.insert - assert it was called exactly once
    client.insert.assert_awaited_once()


@pytest.mark.asyncio
async def test_migrate_skips_already_applied(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    d = runner._ch_dir(cfg)
    _write_migration(d, "0001")

    client = _mock_client(applied={"0001"})
    with patch(_GET_CLIENT, AsyncMock(return_value=client)):
        await runner.migrate(cfg)

    # Only ensure_history is called (command once for CREATE IF NOT EXISTS), no migration commands
    assert client.command.await_count == 1


@pytest.mark.asyncio
async def test_rollback_latest(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    d = runner._ch_dir(cfg)
    _write_migration(d, "0001")

    client = _mock_client(applied={"0001"})
    with patch(_GET_CLIENT, AsyncMock(return_value=client)):
        await runner.rollback(cfg)

    # ensure_history + SELECT 0 command + DELETE
    assert client.command.await_count >= 2
    # remove_applied must issue a DELETE FROM _alchemiq_migrations
    sql_calls = [c.args[0] for c in client.command.call_args_list if c.args]
    assert any("DELETE FROM" in sql for sql in sql_calls), (
        f"rollback did not issue DELETE FROM _alchemiq_migrations - command calls: {sql_calls}"
    )


@pytest.mark.asyncio
async def test_rollback_nothing_to_rollback(tmp_path: Path, capsys) -> None:
    cfg = _cfg(tmp_path)
    d = runner._ch_dir(cfg)
    d.mkdir(parents=True, exist_ok=True)

    client = _mock_client(applied=set())
    with patch(_GET_CLIENT, AsyncMock(return_value=client)):
        await runner.rollback(cfg)

    assert "nothing to roll back" in capsys.readouterr().out.lower()


@pytest.mark.asyncio
async def test_showsql_returns_statements(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    d = runner._ch_dir(cfg)
    _write_migration(d, "0001")

    client = _mock_client(applied=set())
    with patch(_GET_CLIENT, AsyncMock(return_value=client)):
        stmts = await runner.showsql(cfg)

    assert "SELECT 1" in stmts


@pytest.mark.asyncio
async def test_history_cmd_prints_applied(tmp_path: Path, capsys) -> None:
    cfg = _cfg(tmp_path)
    d = runner._ch_dir(cfg)
    _write_migration(d, "0001")

    client = _mock_client(applied={"0001"})
    with patch(_GET_CLIENT, AsyncMock(return_value=client)):
        await runner.history_cmd(cfg)

    out = capsys.readouterr().out
    assert "[x]" in out
    assert "0001" in out


def test_history_command_alias() -> None:
    """history_command is an alias for history_cmd."""
    assert runner.history_command is runner.history_cmd


@pytest.mark.asyncio
async def test_makemigrations_creates_file(tmp_path: Path) -> None:
    """Diff yields one safe CreateTable op -> exactly one 0001_*.py file is written."""
    from alchemiq.migrations.clickhouse.operations import Column, CreateTable

    cfg = _cfg(tmp_path)
    client = _mock_client()

    safe_op = CreateTable("events", (Column("id", "UInt64"),), "ENGINE = MergeTree ORDER BY id")
    _introspect = "alchemiq.migrations.clickhouse.introspect"
    with (
        patch(_GET_CLIENT, AsyncMock(return_value=client)),
        patch("alchemiq.migrations.clickhouse.autogen.diff", return_value=([safe_op], [])),
        patch(f"{_introspect}.live_tables", AsyncMock(return_value=set())),
        patch(f"{_introspect}.live_columns", AsyncMock(return_value={})),
        patch(f"{_introspect}.live_engine", AsyncMock(return_value="")),
    ):
        await runner.makemigrations(cfg, "init")

    ch_dir = runner._ch_dir(cfg)
    files = list(ch_dir.glob("[0-9]*.py"))
    assert len(files) == 1, f"Expected exactly 1 migration file, got: {[f.name for f in files]}"
    assert files[0].name.startswith("0001_"), (
        f"Expected migration filename to start with '0001_', got: {files[0].name}"
    )


@pytest.mark.asyncio
async def test_makemigrations_no_changes_when_db_matches(tmp_path: Path, capsys) -> None:
    """When diff returns empty safe+unsafe, prints no-changes and writes no file."""
    cfg = _cfg(tmp_path)

    client = _mock_client()

    _introspect = "alchemiq.migrations.clickhouse.introspect"
    with (
        patch(_GET_CLIENT, AsyncMock(return_value=client)),
        patch("alchemiq.migrations.clickhouse.autogen.diff", return_value=([], [])),
        patch(f"{_introspect}.live_tables", AsyncMock(return_value=set())),
        patch(f"{_introspect}.live_columns", AsyncMock(return_value={})),
        patch(f"{_introspect}.live_engine", AsyncMock(return_value="")),
    ):
        await runner.makemigrations(cfg, None)

    out = capsys.readouterr().out
    assert "No changes detected" in out
    ch_dir = runner._ch_dir(cfg)
    assert list(ch_dir.glob("[0-9]*.py")) == []


@pytest.mark.asyncio
async def test_showsql_skips_applied_migrations(tmp_path: Path) -> None:
    """The `continue` branch in showsql is exercised when a migration is already applied."""
    cfg = _cfg(tmp_path)
    d = runner._ch_dir(cfg)
    _write_migration(d, "0001")

    client = _mock_client(applied={"0001"})  # "0001" is already applied
    with patch(_GET_CLIENT, AsyncMock(return_value=client)):
        stmts = await runner.showsql(cfg)

    assert stmts == []  # nothing pending


@pytest.mark.asyncio
async def test_makemigrations_unsafe_only_prints_warning(tmp_path: Path, capsys) -> None:
    """When diff returns only unsafe changes (no safe), we print the warning lines."""
    from alchemiq.migrations.clickhouse.autogen import Unsafe

    cfg = _cfg(tmp_path)
    client = _mock_client()

    unsafe_op = Unsafe("change engine", "events  MergeTree -> ReplacingMergeTree")
    _introspect = "alchemiq.migrations.clickhouse.introspect"
    with (
        patch(_GET_CLIENT, AsyncMock(return_value=client)),
        patch("alchemiq.migrations.clickhouse.autogen.diff", return_value=([], [unsafe_op])),
        patch(f"{_introspect}.live_tables", AsyncMock(return_value=set())),
        patch(f"{_introspect}.live_columns", AsyncMock(return_value={})),
        patch(f"{_introspect}.live_engine", AsyncMock(return_value="")),
    ):
        await runner.makemigrations(cfg, None)

    captured = capsys.readouterr()
    assert "change engine" in captured.err
    assert "Skipped" in captured.err
    assert "No safe changes" in captured.out


def test_load_module_raises_when_spec_is_none(monkeypatch, tmp_path: Path) -> None:
    import importlib.util

    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *a, **kw: None)
    with pytest.raises(ValueError, match="cannot load migration module"):
        runner._load_module(tmp_path / "fake.py")


@pytest.mark.asyncio
async def test_makemigrations_pending_guard_warns_and_aborts(tmp_path: Path, capsys) -> None:
    """When there are unapplied migrations, makemigrations warns to stderr and writes no file."""
    cfg = _cfg(tmp_path)
    d = runner._ch_dir(cfg)
    _write_migration(d, "0001")  # a migration file exists with revision "0001"

    client = _mock_client(applied=set())  # "0001" is NOT in applied - pending
    with patch(_GET_CLIENT, AsyncMock(return_value=client)):
        await runner.makemigrations(cfg, "init")

    err = capsys.readouterr().err
    assert "unapplied" in err

    # No new migration file should have been generated
    files = sorted(f.name for f in d.glob("[0-9]*.py"))
    assert files == ["0001_test.py"]
