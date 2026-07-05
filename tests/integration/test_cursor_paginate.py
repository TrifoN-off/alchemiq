from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from alchemiq import Model, Repository
from alchemiq.exceptions import InvalidCursorError
from alchemiq.runtime.session import session_scope
from alchemiq.types import PK, DateTimeTz

pytestmark = pytest.mark.integration


class CurRow(Model):
    __tablename__ = "cursor_row"
    id: PK[int]
    name: str


class CursorDtRow(Model):
    __tablename__ = "cursor_dt_row"
    id: PK[int]
    created_at: DateTimeTz


class SoftCurRow(Model):
    __tablename__ = "cursor_soft_row"
    id: PK[int]
    name: str

    class Meta:
        soft_delete = True


async def _seed(n: int = 5) -> None:
    async with session_scope(write=True) as s:
        s.add_all([CurRow(id=i, name=f"n{i}") for i in range(1, n + 1)])


async def test_forward_paging_covers_all_rows(configured_db) -> None:
    await _seed(5)
    repo = Repository(CurRow)
    seen: list[int] = []
    cursor: str | None = None
    while True:
        page = await repo.order_by("id").cursor_paginate(size=2, after=cursor)
        seen.extend(r.id for r in page.items)
        if not page.has_next:
            break
        cursor = page.next_cursor
    assert seen == [1, 2, 3, 4, 5]


async def test_first_page_flags(configured_db) -> None:
    await _seed(5)
    page = await Repository(CurRow).order_by("id").cursor_paginate(size=2)
    assert [r.id for r in page.items] == [1, 2]
    assert page.has_next is True and page.has_prev is False
    assert page.next_cursor is not None and page.prev_cursor is None


async def test_backward_paging(configured_db) -> None:
    await _seed(5)
    repo = Repository(CurRow)
    p1 = await repo.order_by("id").cursor_paginate(size=2)
    p2 = await repo.order_by("id").cursor_paginate(size=2, after=p1.next_cursor)
    assert [r.id for r in p2.items] == [3, 4]
    back = await repo.order_by("id").cursor_paginate(size=2, before=p2.prev_cursor)
    assert [r.id for r in back.items] == [1, 2]
    assert back.has_next is True


async def test_descending_order(configured_db) -> None:
    await _seed(5)
    page = await Repository(CurRow).order_by("-id").cursor_paginate(size=2)
    assert [r.id for r in page.items] == [5, 4]


async def test_soft_delete_excluded(configured_db) -> None:
    async with session_scope(write=True) as s:
        s.add_all([SoftCurRow(id=i, name=f"n{i}") for i in range(1, 4)])
    repo = Repository(SoftCurRow)
    await repo.delete(2)
    page = await repo.order_by("id").cursor_paginate(size=10)
    assert [r.id for r in page.items] == [1, 3]


async def test_invalid_cursor_raises(configured_db) -> None:
    await _seed(2)
    with pytest.raises(InvalidCursorError):
        await Repository(CurRow).order_by("id").cursor_paginate(size=2, after="!!!bad!!!")


async def test_after_and_before_mutually_exclusive(configured_db) -> None:
    with pytest.raises(ValueError):
        await Repository(CurRow).cursor_paginate(size=2, after="x", before="y")


async def test_backward_into_empty_is_consistent(configured_db) -> None:
    from types import SimpleNamespace

    from alchemiq.query.cursor import effective_order, encode_cursor

    await _seed(1)
    repo = Repository(CurRow)
    order = effective_order(CurRow, ("id",))
    # Encode a cursor pointing at the only row (id=1); paging *before* it returns nothing.
    token = encode_cursor(CurRow, order, SimpleNamespace(id=1))
    back = await repo.order_by("id").cursor_paginate(size=2, before=token)
    assert back.items == []
    assert back.has_next is False
    assert back.next_cursor is None


async def test_forward_empty_table(configured_db) -> None:
    page = await Repository(CurRow).order_by("id").cursor_paginate(size=10)
    assert page.items == []
    assert page.has_next is False and page.has_prev is False
    assert page.next_cursor is None and page.prev_cursor is None


async def test_cursor_over_datetime_with_tiebreaker(configured_db) -> None:
    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    async with session_scope(write=True) as s:
        # ids 1 & 2 share a timestamp - exercises the PK tiebreaker in effective_order
        s.add_all(
            [
                CursorDtRow(id=1, created_at=base),
                CursorDtRow(id=2, created_at=base),
                CursorDtRow(id=3, created_at=base + timedelta(minutes=1)),
                CursorDtRow(id=4, created_at=base + timedelta(minutes=2)),
                CursorDtRow(id=5, created_at=base + timedelta(minutes=3)),
            ]
        )
    repo = Repository(CursorDtRow)
    seen: list[int] = []
    cursor: str | None = None
    while True:
        page = await repo.order_by("created_at").cursor_paginate(size=2, after=cursor)
        seen.extend(r.id for r in page.items)
        if not page.has_next:
            break
        cursor = page.next_cursor
    # All five rows returned - no loss, no duplication
    assert sorted(seen) == [1, 2, 3, 4, 5]
    # Stable order: equal-timestamp rows disambiguated by PK asc; later timestamps follow
    assert seen == [1, 2, 3, 4, 5]
