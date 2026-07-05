from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from alchemiq.migrations.clickhouse import introspect

pytestmark = pytest.mark.unit


def _mock_client() -> MagicMock:
    client = MagicMock()
    client.query = AsyncMock()
    return client


def _result(rows: list) -> MagicMock:
    r = MagicMock()
    r.result_rows = rows
    return r


@pytest.mark.asyncio
async def test_live_tables_returns_set() -> None:
    client = _mock_client()
    client.query.return_value = _result([("events",), ("users",)])
    tables = await introspect.live_tables(client, "mydb")
    assert tables == {"events", "users"}
    client.query.assert_awaited_once()
    assert client.query.call_args.kwargs["parameters"] == {"database": "mydb"}


@pytest.mark.asyncio
async def test_live_columns_returns_dict() -> None:
    client = _mock_client()
    client.query.return_value = _result([("id", "UInt64"), ("name", "String")])
    cols = await introspect.live_columns(client, "mydb", "events")
    assert cols == {"id": "UInt64", "name": "String"}
    assert client.query.call_args.kwargs["parameters"] == {"database": "mydb", "table": "events"}


@pytest.mark.asyncio
async def test_live_engine_returns_engine_name() -> None:
    client = _mock_client()
    client.query.return_value = _result([("MergeTree",)])
    engine = await introspect.live_engine(client, "mydb", "events")
    assert engine == "MergeTree"
    assert client.query.call_args.kwargs["parameters"] == {"database": "mydb", "table": "events"}


@pytest.mark.asyncio
async def test_live_engine_returns_empty_when_no_rows() -> None:
    client = _mock_client()
    client.query.return_value = _result([])
    engine = await introspect.live_engine(client, "mydb", "missing")
    assert engine == ""
