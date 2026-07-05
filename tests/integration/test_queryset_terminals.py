"""Integration tests: QuerySet async terminals - all/first/count/exists.

Uses QuerySet(TermRow) directly.
Seed data is inserted inside session_scope(write=True) per test that needs it.
"""

from __future__ import annotations

import pytest

from alchemiq import Model
from alchemiq.query import QuerySet
from alchemiq.runtime.session import session_scope
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class TermRow(Model):
    __tablename__ = "qs_term_row"
    id: PK[int]
    name: str
    age: int


async def _seed() -> None:
    async with session_scope(write=True) as s:
        s.add_all([TermRow(id=i, name=f"n{i}", age=10 + i) for i in range(1, 6)])


async def test_all_returns_instances(configured_db):
    await _seed()
    rows = await QuerySet(TermRow).filter(age__gte=12).order_by("id").all()
    assert [r.id for r in rows] == [2, 3, 4, 5]
    assert all(isinstance(r, TermRow) for r in rows)


async def test_first_respects_order(configured_db):
    await _seed()
    row = await QuerySet(TermRow).order_by("-age").first()
    assert row is not None and row.id == 5


async def test_first_returns_none_when_empty(configured_db):
    assert await QuerySet(TermRow).filter(name="nope").first() is None


async def test_count(configured_db):
    await _seed()
    assert await QuerySet(TermRow).filter(age__lt=13).count() == 2


async def test_exists(configured_db):
    await _seed()
    assert await QuerySet(TermRow).filter(name="n3").exists() is True
    assert await QuerySet(TermRow).filter(name="zzz").exists() is False
