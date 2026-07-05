import pytest
import pytest_asyncio

from alchemiq.exceptions import EngineNotConfiguredError
from alchemiq.runtime import engine as engine_mod

DSN = "postgresql+asyncpg://u:p@localhost:5432/db"  # never connected to in this test


@pytest_asyncio.fixture(autouse=True)
async def _clean_engine():
    await engine_mod.dispose()
    yield
    await engine_mod.dispose()


def test_require_before_configure_raises():
    with pytest.raises(EngineNotConfiguredError):
        engine_mod.require_sessionmaker()
    with pytest.raises(EngineNotConfiguredError):
        engine_mod.require_engine()


def test_configure_sets_state():
    assert engine_mod.is_configured() is False
    engine_mod.configure(DSN)
    assert engine_mod.is_configured() is True
    assert engine_mod.require_engine() is not None
    assert engine_mod.require_sessionmaker() is not None


async def test_dispose_clears_state():
    engine_mod.configure(DSN)
    await engine_mod.dispose()
    assert engine_mod.is_configured() is False


def test_public_reexports_present():
    import alchemiq.runtime as rt

    for name in ("configure", "dispose", "create_all", "drop_all"):
        assert hasattr(rt, name)
