"""FastAPI lifespan factory for managing the alchemiq engine lifecycle."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from alchemiq.runtime.engine import configure, dispose
from alchemiq.runtime.engine import create_all as create_all_tables


def lifespan(
    dsn: str, *, create_all: bool = False, **engine_kwargs: Any
) -> Callable[[Any], AbstractAsyncContextManager[None]]:
    """Build a FastAPI lifespan that owns the alchemiq engine lifecycle.

    Calls :func:`.configure` on startup and :func:`.dispose` on shutdown.
    Pass the result directly to ``FastAPI(lifespan=...)``.

    E.g.::

        from fastapi import FastAPI
        from alchemiq.fastapi import lifespan

        app = FastAPI(lifespan=lifespan("postgresql+asyncpg://user:pw@host/db"))

        # create tables on startup (dev/test only):
        app = FastAPI(lifespan=lifespan(dsn, create_all=True))

    :param dsn: SQLAlchemy async database URL
        (e.g. ``"postgresql+asyncpg://user:pw@host/db"``).
    :param create_all: when ``True``, run ``CREATE TABLE IF NOT EXISTS`` for all
        registered models before the app starts accepting requests.
    :param engine_kwargs: extra keyword arguments forwarded to
        ``create_async_engine`` (e.g. ``pool_size=10``).
    :return: an async context-manager factory compatible with
        ``FastAPI(lifespan=...)``.

    .. seealso:: :func:`.configure`, :func:`.dispose` - the underlying engine helpers.
    """

    @asynccontextmanager
    async def _cm(app: Any) -> AsyncIterator[None]:
        configure(dsn, **engine_kwargs)
        if create_all:
            await create_all_tables()
        try:
            yield
        finally:
            await dispose()

    return _cm
