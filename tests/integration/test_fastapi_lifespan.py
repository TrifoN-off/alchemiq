"""lifespan configures/disposes the engine; uow & db_session deps drive it."""

from __future__ import annotations

import pytest

from alchemiq.exceptions import EngineNotConfiguredError
from alchemiq.fastapi.deps import db_session, unit_of_work
from alchemiq.fastapi.lifespan import lifespan
from alchemiq.runtime.session import session_scope

pytestmark = pytest.mark.integration


async def test_lifespan_configures_then_disposes(pg_container) -> None:
    cm = lifespan(pg_container.get_connection_url(), create_all=False)
    async with cm(None):
        async with session_scope(write=False) as s:
            assert s is not None
    with pytest.raises(EngineNotConfiguredError):
        async with session_scope(write=False):
            pass


async def test_unit_of_work_dep_yields_active_uow(configured_db) -> None:
    gen = unit_of_work()
    uow = await gen.__anext__()
    assert uow is not None
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()


async def test_db_session_dep_yields_session(configured_db) -> None:
    gen = db_session()
    session = await gen.__anext__()
    assert session is not None
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()
