"""Function-scoped in-memory SQLite fixture for the sqlite suite."""

from __future__ import annotations

import pytest_asyncio

import alchemiq
import tests.sqlite._models  # noqa: F401 - registers the suite's models
from alchemiq.model.registry import metadata
from alchemiq.outbox.capture import connect_outbox
from alchemiq.outbox.models import OutboxEvent
from alchemiq.runtime.engine import require_engine


def _suite_tables():
    tables = [t for name, t in metadata.tables.items() if name.startswith("sq_")]
    tables.append(OutboxEvent.__table__)
    return tables


@pytest_asyncio.fixture
async def sqlite_db():
    """alchemiq configured against in-memory SQLite with the suite's tables created.

    In-memory aiosqlite uses a StaticPool automatically, so every session in the
    test shares one connection and sees the same database.
    """
    alchemiq.configure("sqlite+aiosqlite:///:memory:")
    connect_outbox()  # Re-register outbox handlers in case they were cleared
    engine = require_engine()
    tables = _suite_tables()
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: metadata.create_all(c, tables=tables))
    try:
        yield
    finally:
        await alchemiq.dispose()
