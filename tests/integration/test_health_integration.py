from __future__ import annotations

import pytest

import alchemiq
from alchemiq import check_health

pytestmark = pytest.mark.integration


async def test_postgres_healthy(configured_db) -> None:
    report = await check_health()
    pg = next(c for c in report.components if c.name == "postgres")
    assert pg.healthy is True
    assert pg.latency_ms is not None
    assert report.healthy is True


async def test_cache_healthy(configured_cache) -> None:
    report = await check_health()
    cache = next(c for c in report.components if c.name == "cache")
    assert cache.healthy is True


async def test_postgres_and_cache_together(configured_db, configured_cache) -> None:
    report = await check_health()
    names = {c.name for c in report.components}
    assert {"postgres", "cache"} <= names
    assert report.healthy is True


async def test_unreachable_postgres_is_unhealthy() -> None:
    alchemiq.configure("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    try:
        report = await check_health(timeout=2.0)
        pg = next(c for c in report.components if c.name == "postgres")
        assert pg.healthy is False
        assert pg.error is not None
        assert report.healthy is False
    finally:
        await alchemiq.dispose()
