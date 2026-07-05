"""Async runner that applies, rolls back, and inspects ClickHouse migrations."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

from alchemiq.migrations.clickhouse import history
from alchemiq.migrations.clickhouse.migration import Migration
from alchemiq.migrations.clickhouse.operations import Operations, _repr_double_quotes
from alchemiq.migrations.config import AlchemiqConfig


def _ch_dir(config: AlchemiqConfig) -> Path:
    d = Path(config.root) / config.migrations_dir / "clickhouse"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load migration module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _find_migration(module: Any) -> type[Migration]:
    for value in vars(module).values():
        if isinstance(value, type) and issubclass(value, Migration) and value is not Migration:
            return value
    raise LookupError(f"no Migration subclass in {module.__name__}")


def load_migrations(ch_dir: Path) -> list[Migration]:
    """Load and return all migration instances from *ch_dir*, sorted by revision.

    Scans for files matching ``[0-9]*.py``, imports each, finds the
    :class:`Migration` subclass, instantiates it, and returns the sorted list.
    """
    migrations: list[Migration] = []
    for path in ch_dir.glob("[0-9]*.py"):
        migrations.append(_find_migration(_load_module(path))())
    migrations.sort(key=lambda m: m.revision)
    return migrations


def _ops(migration: Migration, direction: str) -> list[Any]:
    op = Operations()
    getattr(migration, direction)(op)
    return op.operations


async def migrate(config: AlchemiqConfig) -> None:
    """Apply all unapplied migrations to the ClickHouse database.

    Executes each operation's DDL via ``client.command`` and records the
    revision in ``_alchemiq_migrations`` upon success.
    """
    from alchemiq.clickhouse.connection import get_clickhouse_client

    client = await get_clickhouse_client()
    await history.ensure_history(client)
    applied = await history.applied_revisions(client)
    for migration in load_migrations(_ch_dir(config)):
        if migration.revision in applied:
            continue
        for op in _ops(migration, "up"):
            await client.command(op.to_sql())
        await history.record_applied(client, migration.revision, type(migration).__name__)
        print(f"ClickHouse: applied {migration.revision}")


async def rollback(config: AlchemiqConfig) -> None:
    """Revert the most recently applied ClickHouse migration.

    Runs the ``down()`` operations of the latest applied migration and removes
    its record from ``_alchemiq_migrations``.  Prints a message if nothing is
    applied.
    """
    from alchemiq.clickhouse.connection import get_clickhouse_client

    client = await get_clickhouse_client()
    await history.ensure_history(client)
    applied = await history.applied_revisions(client)
    pending = [m for m in load_migrations(_ch_dir(config)) if m.revision in applied]
    if not pending:
        print("ClickHouse: nothing to roll back")
        return
    latest = pending[-1]
    for op in _ops(latest, "down"):
        await client.command(op.to_sql())
    await history.remove_applied(client, latest.revision)
    print(f"ClickHouse: rolled back {latest.revision}")


async def showsql(config: AlchemiqConfig) -> list[str]:
    """Print and return the DDL SQL for all unapplied ClickHouse migrations.

    Connects to ClickHouse to read the applied-revision history (ensuring the
    history table exists) but does **not** execute the pending migration DDL.

    :param config: the resolved project configuration.
    :return: the list of SQL strings that would be executed by ``migrate``.
    """
    from alchemiq.clickhouse.connection import get_clickhouse_client

    client = await get_clickhouse_client()
    await history.ensure_history(client)
    applied = await history.applied_revisions(client)
    statements: list[str] = []
    for migration in load_migrations(_ch_dir(config)):
        if migration.revision in applied:
            continue
        statements.extend(op.to_sql() for op in _ops(migration, "up"))
    for sql in statements:
        print(sql + ";")
    return statements


async def history_cmd(config: AlchemiqConfig) -> None:
    """Print all ClickHouse migrations with ``[x]``/``[ ]`` applied markers."""
    from alchemiq.clickhouse.connection import get_clickhouse_client

    client = await get_clickhouse_client()
    await history.ensure_history(client)
    applied = await history.applied_revisions(client)
    for migration in load_migrations(_ch_dir(config)):
        mark = "x" if migration.revision in applied else " "
        print(f"[{mark}] {migration.revision} {type(migration).__name__}")


# CLI dispatch name is `history`; alias to avoid shadowing the imported module.
history_command = history_cmd


def _next_revision(ch_dir: Path) -> tuple[str, str | None]:
    existing = sorted(p.stem.split("_")[0] for p in ch_dir.glob("[0-9]*.py"))
    if not existing:
        return "0001", None
    head = existing[-1]
    return f"{int(head) + 1:04d}", head


def _stub_for(u: Any) -> str:
    if u.kind == "drop column":
        table, _, col = u.detail.partition(".")
        col = col.split()[0]
        return f"op.drop_column({_repr_double_quotes(table)}, {_repr_double_quotes(col)})"
    if u.kind == "change type":
        return f'op.execute("ALTER TABLE ... MODIFY COLUMN ...")  # {u.detail}'
    return f"# {u.kind}: {u.detail} - write by hand"


def _slugify(message: str | None) -> str:
    """Filesystem-safe migration slug: lowercase, spaces->_, strip non [a-z0-9_].

    Prevents a path-traversal ('/' or '..') in the -m message from writing the
    migration file outside the migrations directory.
    """
    base = (message or "auto").lower().replace(" ", "_")
    cleaned = re.sub(r"[^a-z0-9_]", "", base)
    return cleaned or "auto"


async def makemigrations(config: AlchemiqConfig, message: str | None) -> None:
    """Autogenerate a new ClickHouse migration by diffing models against the live schema.

    Aborts with a warning if there are unapplied migrations - run ``migrate``
    first to keep the diff baseline consistent.  Safe changes (create table,
    add column) are emitted automatically; unsafe ones (drop column, change
    type, change engine, drop table) are written as comment stubs requiring
    manual edits.
    """
    from alchemiq.clickhouse.connection import get_clickhouse_client
    from alchemiq.migrations.clickhouse import autogen, introspect
    from alchemiq.migrations.clickhouse.render import render_migration_source

    ch_dir = _ch_dir(config)
    client = await get_clickhouse_client()
    await history.ensure_history(client)
    applied = await history.applied_revisions(client)
    pending = [m for m in load_migrations(ch_dir) if m.revision not in applied]
    if pending:
        print(
            f"You have {len(pending)} unapplied ClickHouse migration(s); "
            "run `alchemiq migrate` first.",
            file=sys.stderr,
        )
        return
    database = config.clickhouse.database if config.clickhouse else "default"

    tables = await introspect.live_tables(client, database)
    columns = {t: await introspect.live_columns(client, database, t) for t in tables}
    engines = {t: await introspect.live_engine(client, database, t) for t in tables}

    safe, unsafe = autogen.diff(tables, columns, engines)

    if unsafe:
        print(
            "⚠ Skipped changes that require a manual migration (unsafe operations):",
            file=sys.stderr,
        )
        for u in unsafe:
            print(f"  - {u.kind:<13} {u.detail}", file=sys.stderr)

    if not safe:
        if unsafe:
            print("No safe changes to generate; add the above by hand via op.execute(...).")
        else:
            print("No changes detected")
        return

    revision, down_revision = _next_revision(ch_dir)
    slug = _slugify(message)
    down_ops = [autogen.inverse(op) for op in safe]
    stubs = [_stub_for(u) for u in unsafe]
    source = render_migration_source(
        revision=revision,
        down_revision=down_revision,
        class_name=f"Migration{revision}",
        up_ops=safe,
        down_ops=down_ops,
        unsafe_stubs=stubs,
    )
    path = ch_dir / f"{revision}_{slug}.py"
    path.write_text(source, "utf-8")
    print(f"ClickHouse: created migration {path}")
