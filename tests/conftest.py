"""Session-scoped PostgreSQL / ClickHouse testcontainer + function-scoped async fixtures."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.clickhouse import ClickHouseContainer
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

import alchemiq
import alchemiq.cache
from alchemiq.clickhouse.connection import configure_clickhouse, dispose_clickhouse
from alchemiq.clickhouse.ddl import create_clickhouse_tables, drop_clickhouse_tables
from alchemiq.model.registry import metadata

_GROUP_MARKERS = frozenset({"unit", "integration", "clickhouse", "sqlite"})
_DIR_TO_MARKER = {
    "unit": "unit",
    "integration": "integration",
    "clickhouse": "clickhouse",
    "sqlite": "sqlite",
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Fill in a missing group marker from each test's directory.

    The marker-grouped CI gate (`pytest -m unit|integration|clickhouse|sqlite`) silently
    deselects any test file that forgot its `pytestmark` line. Apply the directory's
    marker only to tests that carry none of the group markers; tests with an
    explicit group marker are left untouched (so a unit-marked test under
    tests/clickhouse/ stays unit-only and is not pulled into the slow clickhouse group).
    """
    for item in items:
        if _GROUP_MARKERS.intersection(m.name for m in item.iter_markers()):
            continue
        marker = _DIR_TO_MARKER.get(item.path.parent.name)
        if marker is not None:
            item.add_marker(getattr(pytest.mark, marker))


PG_IMAGE = "postgres:16-alpine"
REDIS_IMAGE = "redis:7-alpine"
CLICKHOUSE_IMAGE = "clickhouse/clickhouse-server:24.8"


@pytest.fixture(scope="session")
def pg_container():
    """Start a Postgres container once for the whole test session."""
    with PostgresContainer(PG_IMAGE, driver="asyncpg") as container:
        yield container


@pytest_asyncio.fixture(scope="function")
async def session(pg_container: PostgresContainer):
    """Async SQLAlchemy session against a fresh schema (create_all / drop_all per test)."""
    url = pg_container.get_connection_url()
    engine = create_async_engine(url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as sess:
            yield sess
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def configured_db(pg_container: PostgresContainer):
    """Configure alchemiq against the container + fresh schema per test."""
    alchemiq.configure(pg_container.get_connection_url())
    await alchemiq.create_all()
    try:
        yield
    finally:
        await alchemiq.drop_all()
        await alchemiq.dispose()


@pytest.fixture(scope="session")
def redis_container():
    """Start a Redis container once for the whole test session."""
    with RedisContainer(REDIS_IMAGE) as container:
        yield container


def _redis_url(container: RedisContainer) -> str:
    host = container.get_container_host_ip()
    port = container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


@pytest_asyncio.fixture(scope="function")
async def configured_cache(redis_container: RedisContainer):
    """Configure a real Redis backend + flush keys between tests."""
    alchemiq.configure_cache(_redis_url(redis_container))
    try:
        yield
    finally:
        cache = alchemiq.cache.get_cache()
        if cache is not None:
            await cache.scan_delete("aq:*")
            if hasattr(cache, "aclose"):
                await cache.aclose()
        alchemiq.reset_cache()


@pytest.fixture(scope="session")
def clickhouse_container():
    """Start a ClickHouse container once for the whole test session."""
    with ClickHouseContainer(CLICKHOUSE_IMAGE) as container:
        yield container


@pytest_asyncio.fixture(scope="function")
async def configured_clickhouse(clickhouse_container: ClickHouseContainer):
    """Configure alchemiq ClickHouse against the container + create/drop tables per test.

    ``create_clickhouse_tables`` materialises ALL tables registered in the process-global
    ``ch_metadata`` - that includes every ``ClickHouseModel`` subclass imported anywhere in
    the test suite, not just the models used by the current test.  Keep every CH test model
    valid (correct engine, non-empty ``order_by``) and uniquely named (both the class name
    and the ``__tablename__`` must be unique across the whole suite) to avoid conflicts here.
    """
    host = clickhouse_container.get_container_host_ip()
    http_port = int(clickhouse_container.get_exposed_port(8123))
    # ClickHouseContainer defaults: username="test", password="test", dbname="test"
    configure_clickhouse(
        host=host,
        port=http_port,
        username=clickhouse_container.username,
        password=clickhouse_container.password,
        database=clickhouse_container.dbname,
    )
    await create_clickhouse_tables()
    try:
        yield
    finally:
        await drop_clickhouse_tables()
        await dispose_clickhouse()
