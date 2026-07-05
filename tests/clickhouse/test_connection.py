import pytest

from alchemiq.clickhouse.connection import (
    configure_clickhouse,
    dispose_clickhouse,
    get_clickhouse_client,
    is_clickhouse_configured,
)
from alchemiq.exceptions import (
    ClickHouseError,
    ClickHouseNotConfiguredError,
    PersistenceError,
    UnsupportedOperationError,
)


@pytest.mark.unit
def test_clickhouse_exceptions_subclass_persistence_error():
    assert issubclass(ClickHouseError, PersistenceError)
    assert issubclass(ClickHouseNotConfiguredError, ClickHouseError)
    assert issubclass(UnsupportedOperationError, ClickHouseError)


@pytest.mark.unit
async def test_get_client_before_configure_raises():
    await dispose_clickhouse()  # ensure clean state
    assert is_clickhouse_configured() is False
    with pytest.raises(ClickHouseNotConfiguredError):
        await get_clickhouse_client()


@pytest.mark.unit
async def test_configure_sets_configured_flag_without_connecting():
    configure_clickhouse(host="localhost", port=8123)
    assert is_clickhouse_configured() is True
    await dispose_clickhouse()
    assert is_clickhouse_configured() is False


@pytest.mark.unit
async def test_concurrent_get_client_creates_single_client(monkeypatch):
    import asyncio
    import sys
    import types

    await dispose_clickhouse()
    created = 0

    class _FakeClient:
        async def close(self):
            pass

    async def _get_async_client(**kw):
        nonlocal created
        created += 1
        await asyncio.sleep(0)  # yield so racers interleave
        return _FakeClient()

    fake = types.ModuleType("clickhouse_connect")
    fake.get_async_client = _get_async_client
    monkeypatch.setitem(sys.modules, "clickhouse_connect", fake)

    configure_clickhouse(host="localhost", port=8123)
    clients = await asyncio.gather(*(get_clickhouse_client() for _ in range(20)))
    assert created == 1
    assert all(c is clients[0] for c in clients)
    await dispose_clickhouse()
