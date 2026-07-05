"""UnitOfWork: reentrant async context manager that owns one database transaction."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import Token
from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession

from alchemiq.runtime.engine import require_sessionmaker
from alchemiq.runtime.post_commit import (
    PostCommitCallback,
    discard_region,
    drain_region,
    open_region,
)
from alchemiq.runtime.session import _active_session


class UnitOfWork:
    """One ``async with`` = one transaction. Autocommit on clean exit, rollback on error.

    Reentrant: a nested :class:`.UnitOfWork` joins the active session and its exit is a
    no-op; only the outermost commits and closes the session.  Use :meth:`.savepoint` for
    partial rollback within a single transaction.

    E.g.::

        # basic usage - commits on clean exit
        async with UnitOfWork() as uow:
            uow.session.add(MyRow(id=1, name="a"))

        # savepoint - inner error rolls back only to the savepoint
        async with UnitOfWork() as uow:
            uow.session.add(MyRow(id=3, name="keep"))
            await uow.session.flush()
            async with uow.savepoint():
                uow.session.add(MyRow(id=4, name="drop"))
                raise RuntimeError("inner")  # only the savepoint is rolled back

        # reentrant - nested UoW joins the outer session
        async with UnitOfWork() as outer:
            async with UnitOfWork() as inner:
                assert inner.session is outer.session  # same session, no-op exit

    .. seealso:: :meth:`.UnitOfWork.savepoint` - nested savepoint for partial rollback.
    """

    session: AsyncSession

    def __init__(self) -> None:
        self._joined: bool = False
        self._token: Token[AsyncSession | None] | None = None
        self._pc_token: Token[list[PostCommitCallback] | None] | None = None

    async def __aenter__(self) -> UnitOfWork:
        existing = _active_session.get()
        if existing is not None:
            self._joined = True
            self.session = existing
            return self
        session = require_sessionmaker()()
        try:
            self._token = _active_session.set(session)
        except Exception:
            await session.close()
            raise
        self.session = session
        self._pc_token = open_region()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        if self._joined:
            return False  # inner UoW: outermost owns commit/close
        committed = False
        try:
            if exc_type is None:
                await self.session.commit()
                committed = True
            else:
                await self.session.rollback()
        finally:
            await self.session.close()
            if self._token is not None:
                _active_session.reset(self._token)
            if committed:
                await drain_region(self._pc_token)
            else:
                discard_region(self._pc_token)
        return False

    async def commit(self) -> None:
        """Flush and commit the current transaction.

        :raises RuntimeError: if called on a nested (joined) :class:`.UnitOfWork` - only
            the outermost may commit.
        """
        if self._joined:
            raise RuntimeError(
                "cannot commit a joined UnitOfWork; the outermost UnitOfWork owns the transaction"
            )
        await self.session.commit()

    async def rollback(self) -> None:
        """Abort the current transaction without closing the session.

        :raises RuntimeError: if called on a nested (joined) :class:`.UnitOfWork`.  Raise
            an exception to abort the outer transaction instead, or use
            :meth:`.savepoint` for partial rollback.
        """
        if self._joined:
            raise RuntimeError(
                "cannot roll back a joined UnitOfWork; raise an exception to abort, "
                "or use uow.savepoint() for partial rollback"
            )
        await self.session.rollback()

    @asynccontextmanager
    async def savepoint(self) -> AsyncIterator[None]:
        """Yield a nested savepoint; rolls back only to this point on error.

        E.g.::

            async with UnitOfWork() as uow:
                uow.session.add(MyRow(id=1, name="keep"))
                await uow.session.flush()
                async with uow.savepoint():
                    uow.session.add(MyRow(id=2, name="drop"))
                    raise RuntimeError("abort inner")  # only savepoint rolled back
                # id=1 is still pending; commits with the outer transaction
        """
        async with self.session.begin_nested():
            yield
