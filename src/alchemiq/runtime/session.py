"""Session context: ``get_active_session`` and ``session_scope`` for implicit ambient sessions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar

from sqlalchemy.ext.asyncio import AsyncSession

from alchemiq.runtime.engine import require_sessionmaker

_active_session: ContextVar[AsyncSession | None] = ContextVar(
    "alchemiq_active_session", default=None
)


def get_active_session() -> AsyncSession | None:
    """Return the session owned by the current ``UnitOfWork``, or ``None`` if none is active."""
    return _active_session.get()


@asynccontextmanager
async def session_scope(*, write: bool) -> AsyncIterator[AsyncSession]:
    """Yield the ambient UoW session, or a short-lived autocommit session."""
    active = _active_session.get()
    if active is not None:
        yield active  # owned by the UnitOfWork - do not commit/close here
        return
    from alchemiq.runtime.post_commit import discard_region, drain_region, open_region

    sessionmaker = require_sessionmaker()
    token = open_region() if write else None
    try:
        async with sessionmaker() as session:
            yield session
            if write:
                await session.commit()
        await drain_region(token)
    except BaseException:
        discard_region(token)
        raise
