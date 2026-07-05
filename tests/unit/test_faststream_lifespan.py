from __future__ import annotations

import pytest
import pytest_asyncio

from alchemiq.faststream import lifespan
from alchemiq.runtime import engine as engine_mod
from alchemiq.runtime.engine import is_configured

pytestmark = pytest.mark.unit


@pytest_asyncio.fixture(autouse=True)
async def _clean_engine() -> None:
    await engine_mod.dispose()
    yield
    await engine_mod.dispose()


async def test_lifespan_configures_then_disposes() -> None:
    # create_async_engine is lazy - a well-formed DSN configures without connecting.
    assert not is_configured()
    cm = lifespan("postgresql+asyncpg://u:p@localhost:5432/db", create_all=False)
    async with cm():  # factory ignores the (absent) FastStream context arg
        assert is_configured()
    assert not is_configured()
