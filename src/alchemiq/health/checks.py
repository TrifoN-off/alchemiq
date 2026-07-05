"""Async health probes for configured alchemiq backends (Postgres, ClickHouse, cache)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable
from typing import TYPE_CHECKING

from sqlalchemy import text

from alchemiq.cache import get_cache
from alchemiq.health.report import ComponentHealth, HealthReport
from alchemiq.runtime.engine import is_configured, require_engine

if TYPE_CHECKING:
    from alchemiq.cache import CacheBackend


def _short(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:200]


def _clickhouse_configured() -> bool:
    try:
        from alchemiq.clickhouse.connection import is_clickhouse_configured
    except ImportError:
        return False
    return is_clickhouse_configured()


def _ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0


async def _probe_postgres(timeout: float) -> ComponentHealth:
    start = time.perf_counter()
    try:
        engine = require_engine()
        async with asyncio.timeout(timeout):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        return ComponentHealth("postgres", True, _ms(start))
    except Exception as exc:
        return ComponentHealth("postgres", False, None, _short(exc))


async def _probe_clickhouse(timeout: float) -> ComponentHealth:
    start = time.perf_counter()
    try:
        from alchemiq.clickhouse.connection import get_clickhouse_client

        async with asyncio.timeout(timeout):
            client = await get_clickhouse_client()
            ok = await client.ping()
        if not ok:
            raise RuntimeError("clickhouse ping returned False")
        return ComponentHealth("clickhouse", True, _ms(start))
    except Exception as exc:
        return ComponentHealth("clickhouse", False, None, _short(exc))


async def _probe_cache(backend: CacheBackend, timeout: float) -> ComponentHealth:
    start = time.perf_counter()
    try:
        async with asyncio.timeout(timeout):
            await backend.get("aq:__health__")
        return ComponentHealth("cache", True, _ms(start))
    except Exception as exc:
        return ComponentHealth("cache", False, None, _short(exc))


async def check_health(*, timeout: float = 5.0) -> HealthReport:
    """Run health probes for all configured backends concurrently.

    Returns a :class:`.HealthReport` aggregating all component results.
    Probes are skipped for backends that are not configured.  :attr:`.HealthReport.healthy`
    is ``True`` only if **every** component probe succeeds.  Each probe is guarded by
    ``timeout`` seconds; a probe that times out or errors is recorded as unhealthy.

    E.g.::

        from alchemiq.health import check_health

        report = await check_health()
        if not report.healthy:
            print(report.to_dict())

        # FastAPI integration:
        from alchemiq.fastapi import health_router
        app.include_router(health_router())

    :param timeout: per-probe timeout in seconds (default 5.0).
    :return: a :class:`.HealthReport` aggregating all component results.

    .. note::

        When no backends are configured, returns a trivially healthy report with an empty
        ``components`` tuple - useful in unit tests that haven't called ``configure``.

    .. seealso:: :class:`.HealthReport` - the returned aggregate report.
    """
    probes: list[Awaitable[ComponentHealth]] = []
    if is_configured():
        probes.append(_probe_postgres(timeout))
    if _clickhouse_configured():
        probes.append(_probe_clickhouse(timeout))
    backend = get_cache()
    if backend is not None:
        probes.append(_probe_cache(backend, timeout))

    if not probes:
        return HealthReport(healthy=True, components=())
    components = tuple(await asyncio.gather(*probes))
    return HealthReport(healthy=all(c.healthy for c in components), components=components)
