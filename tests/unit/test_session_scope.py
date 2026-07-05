import pytest
import pytest_asyncio

from alchemiq.exceptions import EngineNotConfiguredError
from alchemiq.runtime import engine as engine_mod
from alchemiq.runtime.session import _active_session, get_active_session, session_scope


@pytest_asyncio.fixture(autouse=True)
async def _clean_engine():
    await engine_mod.dispose()
    yield
    await engine_mod.dispose()


async def test_scope_yields_active_contextvar_session():
    sentinel = object()
    token = _active_session.set(sentinel)  # pretend a UoW is active
    try:
        async with session_scope(write=True) as s:
            assert s is sentinel  # reused, not a new session
        assert get_active_session() is sentinel  # not closed/reset by the scope
    finally:
        _active_session.reset(token)


async def test_scope_without_engine_raises():
    assert get_active_session() is None
    with pytest.raises(EngineNotConfiguredError):
        async with session_scope(write=False):
            pass
