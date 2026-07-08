"""Dialect helpers: which backend a bind talks to, and what is PostgreSQL-only.

The SQLite dev/test tier keeps every unsupported path loud and uniform: all
"PostgreSQL-only" refusals across the codebase produce the same message shape
via :func:`require_postgres`, and a missing async driver fails at
``configure()`` time with an actionable install hint.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import URL

from alchemiq.exceptions import ConfigError

_MATRIX_HINT = "see the SQLite feature matrix in the alchemiq documentation"

_DRIVERS = {"asyncpg": ("asyncpg", "postgres"), "aiosqlite": ("aiosqlite", "sqlite")}


def dialect_of(bind: Any) -> str:
    """Return the dialect name (``"postgresql"``, ``"sqlite"``, ...) of *bind*.

    *bind* is anything carrying a ``.dialect`` attribute: ``Engine``,
    ``AsyncEngine``, or ``Connection``.
    """
    return bind.dialect.name


def insert_for(bind: Any) -> Any:
    """Return the dialect-specific ``insert()`` construct for *bind*.

    Both the PostgreSQL and SQLite inserts expose ``on_conflict_do_update`` /
    ``on_conflict_do_nothing`` with equivalent semantics (SQLite >= 3.24).
    """
    if dialect_of(bind) == "sqlite":
        return sqlite_insert
    return pg_insert


def require_postgres(feature: str, bind: Any, *, exc: type[Exception] = ConfigError) -> None:
    """Raise *exc* with the uniform PostgreSQL-only message when *bind* is not PostgreSQL."""
    name = dialect_of(bind)
    if name != "postgresql":
        raise exc(f"{feature} is PostgreSQL-only (current dialect: {name}); {_MATRIX_HINT}")


def ensure_async_driver(url: URL) -> None:
    """Fail fast with an install hint when the async driver for *url* is missing.

    Only the bundled drivers (``asyncpg``, ``aiosqlite``) are checked; DSNs with
    any other explicit driver (e.g. ``postgresql+psycopg://``) pass through
    untouched - an unrecognized driver fails naturally in
    ``create_async_engine`` instead.

    :raises ConfigError: when the bundled driver module cannot be imported.
    """
    hit = _DRIVERS.get(url.get_driver_name())
    if hit is None:
        return
    module, extra = hit
    try:
        __import__(module)
    except ImportError as e:
        raise ConfigError(
            f"the {module!r} driver is required for {url.get_backend_name()} DSNs; "
            f"install it with: pip install alchemiq[{extra}]"
        ) from e
