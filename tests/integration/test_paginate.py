"""Integration tests: QuerySet.paginate - offset pagination.

Uses QuerySet(PgRow) directly.
Seed data is inserted inside session_scope(write=True) per test.
"""

from __future__ import annotations

import pytest

from alchemiq import Model
from alchemiq.query import QuerySet
from alchemiq.runtime.session import session_scope
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class PgRow(Model):
    __tablename__ = "page_pg_row"
    id: PK[int]
    name: str


async def _seed(n: int) -> None:
    async with session_scope(write=True) as s:
        s.add_all([PgRow(id=i, name=f"n{i}") for i in range(1, n + 1)])


async def test_paginate_second_page(configured_db):
    await _seed(5)
    page = await QuerySet(PgRow).order_by("id").paginate(page=2, size=2)
    assert [r.id for r in page.items] == [3, 4]
    assert page.total == 5
    assert page.pages == 3
    assert page.has_next is True
    assert page.has_prev is True


async def test_paginate_invalid_args(configured_db):
    with pytest.raises(ValueError):
        await QuerySet(PgRow).paginate(page=0, size=10)
