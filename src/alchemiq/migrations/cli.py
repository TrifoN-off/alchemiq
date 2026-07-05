"""CLI entry point: ``alchemiq makemigrations|migrate|rollback|history|showsql``."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable
from typing import Any

from alchemiq.migrations.config import AlchemiqConfig, import_models, load_config
from alchemiq.migrations.errors import MigrationConfigError

_COMMANDS = ("makemigrations", "migrate", "rollback", "history", "showsql")


def build_parser() -> argparse.ArgumentParser:
    """Build the ``alchemiq`` argument parser with all sub-commands."""
    parser = argparse.ArgumentParser(prog="alchemiq", description="alchemiq migrations")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in _COMMANDS:
        sp = sub.add_parser(name)
        sp.add_argument("--db", choices=("postgres", "clickhouse"), default=None)
        if name == "makemigrations":
            sp.add_argument("-m", "--message", default=None)
    return parser


def _pg_makemigrations(cfg: AlchemiqConfig, message: str | None) -> None:
    from alchemiq.migrations.postgres import backend  # ty: ignore[unresolved-import]

    backend.makemigrations(cfg, message)


def _pg_migrate(cfg: AlchemiqConfig) -> None:
    from alchemiq.migrations.postgres import backend  # ty: ignore[unresolved-import]

    backend.migrate(cfg)


def _pg_rollback(cfg: AlchemiqConfig) -> None:
    from alchemiq.migrations.postgres import backend  # ty: ignore[unresolved-import]

    backend.rollback(cfg)


def _pg_history(cfg: AlchemiqConfig) -> None:
    from alchemiq.migrations.postgres import backend  # ty: ignore[unresolved-import]

    backend.history(cfg)


def _pg_showsql(cfg: AlchemiqConfig) -> None:
    from alchemiq.migrations.postgres import backend  # ty: ignore[unresolved-import]

    backend.showsql(cfg)


async def _run_with_clickhouse(cfg: AlchemiqConfig, run: Callable[[], Awaitable[Any]]) -> None:
    """Run a ClickHouse migration coroutine with the global client configured.

    Configures the process-global ClickHouse client from the parsed
    ``[tool.alchemiq.clickhouse]`` settings before invoking *run*, and disposes
    it afterwards.  If the application already configured a client in-process
    (``is_clickhouse_configured()`` is ``True``), the existing configuration is
    left untouched and is NOT disposed - the CLI only manages a client it
    created itself.
    """
    from alchemiq.clickhouse import connection  # ty: ignore[unresolved-import]

    owns_client = False
    settings = cfg.clickhouse
    if settings is not None and not connection.is_clickhouse_configured():
        connection.configure_clickhouse(**settings.client_kwargs)
        owns_client = True
    try:
        await run()
    finally:
        if owns_client:
            await connection.dispose_clickhouse()


def _ch_makemigrations(cfg: AlchemiqConfig, message: str | None) -> None:
    from alchemiq.migrations.clickhouse import runner  # ty: ignore[unresolved-import]

    asyncio.run(_run_with_clickhouse(cfg, lambda: runner.makemigrations(cfg, message)))


def _ch_migrate(cfg: AlchemiqConfig) -> None:
    from alchemiq.migrations.clickhouse import runner  # ty: ignore[unresolved-import]

    asyncio.run(_run_with_clickhouse(cfg, lambda: runner.migrate(cfg)))


def _ch_rollback(cfg: AlchemiqConfig) -> None:
    from alchemiq.migrations.clickhouse import runner  # ty: ignore[unresolved-import]

    asyncio.run(_run_with_clickhouse(cfg, lambda: runner.rollback(cfg)))


def _ch_history(cfg: AlchemiqConfig) -> None:
    from alchemiq.migrations.clickhouse import runner  # ty: ignore[unresolved-import]

    asyncio.run(_run_with_clickhouse(cfg, lambda: runner.history_command(cfg)))


def _ch_showsql(cfg: AlchemiqConfig) -> None:
    from alchemiq.migrations.clickhouse import runner  # ty: ignore[unresolved-import]

    asyncio.run(_run_with_clickhouse(cfg, lambda: runner.showsql(cfg)))


# Fallback extras hint per --db target when the missing module is unknown.
# PostgreSQL migrations need BOTH the asyncpg driver and Alembic.
_EXTRA = {"postgres": "postgres,migrations", "clickhouse": "clickhouse"}

# Known missing top-level modules -> the extra that provides them.
_MODULE_EXTRA = {
    "asyncpg": "postgres",
    "alembic": "migrations",
    "clickhouse_connect": "clickhouse",
    "clickhouse_sqlalchemy": "clickhouse",
    "aiohttp": "clickhouse",  # clickhouse-connect[async] pulls it in
}


def _install_hint(db: str, exc: ImportError) -> str:
    """Map an ImportError to the ``alchemiq[...]`` extra that fixes it.

    Prefers ``exc.name`` (set by ``ModuleNotFoundError``); falls back to
    scanning the message for a known module name (some libraries re-raise
    plain ``ImportError`` without ``name``, e.g. clickhouse-connect for a
    missing ``aiohttp``).  Defaults to the per-database extras in ``_EXTRA``.
    """
    root = (getattr(exc, "name", None) or "").partition(".")[0]
    if root not in _MODULE_EXTRA:
        msg = str(exc)
        root = next((mod for mod in _MODULE_EXTRA if mod in msg), "")
    extra = _MODULE_EXTRA.get(root, _EXTRA[db])
    return f"pip install 'alchemiq[{extra}]'"


def _run_one(db: str, command: str, cfg: AlchemiqConfig, message: str | None) -> None:
    dispatch: dict[str, dict[str, Callable[..., Any]]] = {
        "postgres": {
            "makemigrations": _pg_makemigrations,
            "migrate": _pg_migrate,
            "rollback": _pg_rollback,
            "history": _pg_history,
            "showsql": _pg_showsql,
        },
        "clickhouse": {
            "makemigrations": _ch_makemigrations,
            "migrate": _ch_migrate,
            "rollback": _ch_rollback,
            "history": _ch_history,
            "showsql": _ch_showsql,
        },
    }
    handler = dispatch[db][command]
    if command == "makemigrations":
        handler(cfg, message)
    else:
        handler(cfg)


def main(argv: list[str] | None = None) -> int:
    """Run the alchemiq CLI.

    Parses *argv* (defaults to ``sys.argv[1:]``), loads config, and dispatches
    to the appropriate PG or CH handler for each configured database.

    E.g.::

        alchemiq makemigrations -m init
        alchemiq migrate --db postgres
        alchemiq rollback --db clickhouse
        alchemiq history
        alchemiq showsql

    :param argv: argument list; defaults to ``sys.argv[1:]`` when ``None``.
    :return: ``0`` on success, ``1`` on a runtime error, ``2`` on a configuration error.
    """
    ns = build_parser().parse_args(argv)
    try:
        cfg = load_config()
        import_models(cfg)
    except MigrationConfigError as e:
        print(str(e), file=sys.stderr)
        return 2
    except Exception as e:  # unexpected errors from load_config
        print(str(e), file=sys.stderr)
        return 2

    configured = [db for db, s in (("postgres", cfg.postgres), ("clickhouse", cfg.clickhouse)) if s]
    if ns.db is not None:
        if ns.db not in configured:
            print(f"{ns.db} is not configured in [tool.alchemiq.{ns.db}]", file=sys.stderr)
            return 2
        targets = [ns.db]
    else:
        targets = configured
        skipped = [db for db in ("postgres", "clickhouse") if db not in configured]
        for db in skipped:
            print(f"skipping {db}: not configured in [tool.alchemiq.{db}]", file=sys.stderr)
        if not targets:
            print("no database configured under [tool.alchemiq]", file=sys.stderr)
            return 2

    message = getattr(ns, "message", None)
    for db in targets:
        try:
            _run_one(db, ns.command, cfg, message)
        except ImportError as e:
            print(
                f"{db} migrations need an extra: {_install_hint(db, e)} ({e})",
                file=sys.stderr,
            )
            return 1
        except Exception as e:  # surface a clean message, non-zero exit
            print(f"error ({db} {ns.command}): {e}", file=sys.stderr)
            return 1
    return 0
