"""Type roundtrips on SQLite: UUID, JSON, Maybe[JSON], Enum, aware datetimes."""

from __future__ import annotations

import datetime as dt
import uuid

from alchemiq import Repository
from tests.sqlite._models import SqColor, SqKitchen

_TS = dt.datetime(2026, 7, 8, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=3)))


async def _create(**overrides):
    values = {
        "id": 1,
        "payload": {"a": [1, 2], "b": {"c": True}},
        "color": SqColor.red,
        "seen_at": _TS,
    }
    values.update(overrides)
    return await Repository(SqKitchen).create(**values)


async def test_uuid_columns_return_uuid_objects(sqlite_db) -> None:
    await _create()
    row = await Repository(SqKitchen).get(id=1)
    assert isinstance(row.ref4, uuid.UUID)
    assert isinstance(row.ref7, uuid.UUID)


async def test_json_roundtrip(sqlite_db) -> None:
    await _create()
    row = await Repository(SqKitchen).get(id=1)
    assert row.payload == {"a": [1, 2], "b": {"c": True}}


async def test_maybe_json_roundtrip(sqlite_db) -> None:
    await _create(meta={"k": 1})
    row = await Repository(SqKitchen).get(id=1)
    assert row.meta.is_some
    assert row.meta.unwrap() == {"k": 1}


async def test_enum_roundtrip(sqlite_db) -> None:
    await _create()
    row = await Repository(SqKitchen).get(id=1)
    assert row.color is SqColor.red


async def test_datetimes_come_back_timezone_aware(sqlite_db) -> None:
    await _create()
    row = await Repository(SqKitchen).get(id=1)
    assert row.seen_at.tzinfo is not None
    assert row.seen_at == _TS  # same instant, normalized to UTC
    assert row.created_at.tzinfo is not None  # server_default CURRENT_TIMESTAMP path
    assert row.updated_at.tzinfo is not None
