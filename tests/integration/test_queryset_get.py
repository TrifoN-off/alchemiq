"""Integration tests: QuerySet.get / get_or_none / last.

Uses QuerySet(GetRow) directly.
Seed data is inserted inside session_scope(write=True) per test that needs it.
"""

from __future__ import annotations

import pytest

from alchemiq import Model
from alchemiq.exceptions import MultipleResultsFound, NotFoundError
from alchemiq.query import QuerySet
from alchemiq.runtime.session import session_scope
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class GetRow(Model):
    __tablename__ = "qs_get_row"
    id: PK[int]
    name: str
    tag: str


async def _seed() -> None:
    async with session_scope(write=True) as s:
        s.add_all(
            [
                GetRow(id=1, name="a", tag="x"),
                GetRow(id=2, name="b", tag="x"),
                GetRow(id=3, name="c", tag="y"),
            ]
        )


async def test_get_one(configured_db):
    await _seed()
    row = await QuerySet(GetRow).get(id=2)
    assert row.name == "b"


async def test_get_missing_raises_not_found(configured_db):
    await _seed()
    with pytest.raises(NotFoundError):
        await QuerySet(GetRow).get(id=99)


async def test_get_multiple_raises(configured_db):
    await _seed()
    with pytest.raises(MultipleResultsFound):
        await QuerySet(GetRow).get(tag="x")


async def test_get_or_none_returns_none(configured_db):
    await _seed()
    result = await QuerySet(GetRow).get_or_none(id=99)
    assert result is None


async def test_get_or_none_returns_row(configured_db):
    await _seed()
    row = await QuerySet(GetRow).get_or_none(id=3)
    assert row is not None
    assert row.name == "c"


async def test_get_or_none_multiple_raises(configured_db):
    await _seed()
    with pytest.raises(MultipleResultsFound):
        await QuerySet(GetRow).get_or_none(tag="x")


async def test_last_uses_pk_when_unordered(configured_db):
    await _seed()
    row = await QuerySet(GetRow).last()
    assert row is not None
    assert row.id == 3


async def test_last_reverses_order(configured_db):
    await _seed()
    row = await QuerySet(GetRow).order_by("id").last()
    assert row is not None
    assert row.id == 3


async def test_last_reverses_descending_order(configured_db):
    await _seed()
    row = await QuerySet(GetRow).order_by("-id").last()
    assert row is not None
    assert row.id == 1


async def test_last_empty_returns_none(configured_db):
    result = await QuerySet(GetRow).last()
    assert result is None
