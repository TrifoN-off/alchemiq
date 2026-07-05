"""Process-global async engine and sessionmaker: configure, dispose, create/drop DDL."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from alchemiq.exceptions import EngineNotConfiguredError
from alchemiq.model.registry import metadata

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def configure(dsn: str, *, echo: bool = False, **engine_kwargs: Any) -> None:
    """Create the process-global async engine + sessionmaker. Call once at startup.

    Stores the engine and sessionmaker as module-level singletons used by every
    :class:`.UnitOfWork` and ``session_scope`` call.  A second call replaces them (useful
    in tests that cycle databases).

    E.g.::

        # pytest conftest.py - set up once per session
        alchemiq.configure(pg_container.get_connection_url())
        await alchemiq.create_all()

        # application lifespan
        alchemiq.configure(os.environ["DATABASE_URL"], echo=False)

    :param dsn: async-compatible SQLAlchemy DSN, e.g. ``postgresql+asyncpg://...``.
    :param echo: when ``True``, the engine logs all SQL statements (useful for debugging).
    :param engine_kwargs: additional keyword arguments forwarded to
        ``create_async_engine`` (e.g. ``pool_size``,
        ``max_overflow``).
    """
    from alchemiq.runtime.soft_delete_filter import AlchemiqSession

    global _engine, _sessionmaker
    _engine = create_async_engine(dsn, echo=echo, **engine_kwargs)
    _sessionmaker = async_sessionmaker(
        _engine, expire_on_commit=False, sync_session_class=AlchemiqSession
    )


def is_configured() -> bool:
    """Return ``True`` if ``configure()`` has been called and the engine is active."""
    return _sessionmaker is not None


def require_engine() -> AsyncEngine:
    """Return the active engine, raising ``EngineNotConfiguredError`` if not yet configured."""
    if _engine is None:
        raise EngineNotConfiguredError(
            "alchemiq is not configured; call alchemiq.configure(dsn) first"
        )
    return _engine


def require_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the active sessionmaker, raising ``EngineNotConfiguredError`` if not configured."""
    if _sessionmaker is None:
        raise EngineNotConfiguredError(
            "alchemiq is not configured; call alchemiq.configure(dsn) first"
        )
    return _sessionmaker


async def dispose() -> None:
    """Dispose the engine and clear state (lifespan shutdown / test teardown)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def create_all() -> None:
    """Create all mapped tables in the database (DDL CREATE IF NOT EXISTS)."""
    engine = require_engine()
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)


async def drop_all() -> None:
    """Drop all mapped tables from the database (DDL DROP IF EXISTS). Destructive."""
    engine = require_engine()
    async with engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)
