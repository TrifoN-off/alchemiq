"""FastStream lifespan factory for managing the alchemiq engine lifecycle."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from alchemiq.runtime.engine import configure, dispose
from alchemiq.runtime.engine import create_all as create_all_tables


def lifespan(
    dsn: str, *, create_all: bool = False, **engine_kwargs: Any
) -> Callable[..., AbstractAsyncContextManager[None]]:
    """Build a FastStream lifespan that owns the alchemiq engine lifecycle.

    Calls :func:`.configure` on startup and :func:`.dispose` on shutdown.
    The returned factory absorbs whatever context argument FastStream passes (or none),
    so it is compatible with all FastStream broker and app variants.

    E.g.::

        from faststream import FastStream
        from faststream.rabbit import RabbitBroker
        from alchemiq.faststream import lifespan

        broker = RabbitBroker("amqp://guest:guest@localhost/")
        app = FastStream(broker, lifespan=lifespan("postgresql+asyncpg://u:p@h/db"))

        # create tables on startup (dev/test only):
        app = FastStream(broker, lifespan=lifespan(dsn, create_all=True))

    :param dsn: SQLAlchemy async database URL
        (e.g. ``"postgresql+asyncpg://user:pw@host/db"``).
    :param create_all: when ``True``, run ``CREATE TABLE IF NOT EXISTS`` for all
        registered models before the broker starts consuming.
    :param engine_kwargs: extra keyword arguments forwarded to
        ``create_async_engine`` (e.g. ``pool_size=5``).
    :return: an async context-manager factory compatible with
        ``FastStream(lifespan=...)``.

    .. seealso:: :func:`.configure`, :func:`.dispose` - the underlying engine helpers.
    """

    @asynccontextmanager
    async def _cm(*_args: Any, **_kwargs: Any) -> AsyncIterator[None]:
        configure(dsn, **engine_kwargs)
        if create_all:
            await create_all_tables()
        try:
            yield
        finally:
            await dispose()

    return _cm
