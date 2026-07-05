"""FastAPI / FastStream dependency providers: repository, unit_of_work, and db_session."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from alchemiq.repository import Repository
from alchemiq.runtime.session import session_scope
from alchemiq.runtime.unit_of_work import UnitOfWork


def resolve_repository(repo_or_model: Any) -> Repository:
    """Return a ``Repository`` from a repository instance, subclass, or model class."""
    if isinstance(repo_or_model, Repository):
        return repo_or_model
    if isinstance(repo_or_model, type) and issubclass(repo_or_model, Repository):
        return repo_or_model()
    return Repository(repo_or_model)


def repository(repo_or_model: Any) -> Callable[[], Repository]:
    """Return a zero-arg callable that yields the resolved repository (use as a DI default)."""
    repo = resolve_repository(repo_or_model)

    def _provide() -> Repository:
        return repo

    return _provide


async def unit_of_work() -> AsyncIterator[UnitOfWork]:
    """Yield a ``UnitOfWork`` scoped to the request (FastAPI/FastStream dependency)."""
    async with UnitOfWork() as uow:
        yield uow


async def db_session() -> AsyncIterator[AsyncSession]:
    """Yield a read-only ``AsyncSession`` scoped to the request (FastAPI/FastStream dependency)."""
    async with session_scope(write=False) as session:
        yield session
