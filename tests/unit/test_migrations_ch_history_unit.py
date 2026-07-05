from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from alchemiq.migrations.clickhouse import history

pytestmark = pytest.mark.unit


def _mock_client() -> MagicMock:
    client = MagicMock()
    client.command = AsyncMock()
    client.query = AsyncMock()
    client.insert = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_ensure_history_issues_create() -> None:
    client = _mock_client()
    await history.ensure_history(client)
    client.command.assert_awaited_once()
    sql = client.command.call_args[0][0]
    assert history.HISTORY_TABLE in sql


@pytest.mark.asyncio
async def test_applied_revisions_returns_set() -> None:
    client = _mock_client()
    result = MagicMock()
    result.result_rows = [("0001",), ("0002",)]
    client.query.return_value = result
    revs = await history.applied_revisions(client)
    assert revs == {"0001", "0002"}


@pytest.mark.asyncio
async def test_record_applied_inserts_row() -> None:
    client = _mock_client()
    await history.record_applied(client, "0001", "Migration0001")
    client.insert.assert_awaited_once_with(
        history.HISTORY_TABLE, [["0001", "Migration0001"]], column_names=["revision", "name"]
    )


@pytest.mark.asyncio
async def test_remove_applied_issues_delete() -> None:
    client = _mock_client()
    await history.remove_applied(client, "0001")
    client.command.assert_awaited_once()
    sql = client.command.call_args[0][0]
    assert "DELETE" in sql
    assert history.HISTORY_TABLE in sql
