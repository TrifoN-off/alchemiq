"""Core query behaviour on SQLite: CRUD, filters, ordering, both paginations."""

from __future__ import annotations

from alchemiq import Q, QuerySet, Repository
from tests.sqlite._models import SqNote


async def _seed(n: int = 5) -> None:
    repo = Repository(SqNote)
    for i in range(1, n + 1):
        await repo.create(id=i, title=f"note {i}", rank=i)


async def test_crud_cycle(sqlite_db) -> None:
    repo = Repository(SqNote)
    await repo.create(id=1, title="first", rank=10)
    row = await repo.get(id=1)
    assert row.title == "first"
    updated = await repo.update(1, title="renamed")
    assert updated.title == "renamed"
    await repo.delete(1)
    assert await QuerySet(SqNote).filter(id=1).exists() is False


async def test_filter_lookups_and_q(sqlite_db) -> None:
    await _seed()
    assert await QuerySet(SqNote).filter(rank__gte=4).count() == 2
    assert await QuerySet(SqNote).filter(title__contains="note").count() == 5
    assert await QuerySet(SqNote).exclude(rank=1).count() == 4
    both = await QuerySet(SqNote).filter(Q(rank=1) | Q(rank=5)).all()
    assert {r.rank for r in both} == {1, 5}


async def test_order_by_and_slicing(sqlite_db) -> None:
    await _seed()
    rows = await QuerySet(SqNote).order_by("-rank").limit(2).all()
    assert [r.rank for r in rows] == [5, 4]


async def test_offset_pagination(sqlite_db) -> None:
    await _seed()
    page = await QuerySet(SqNote).order_by("rank").paginate(page=2, size=2)
    assert [r.rank for r in page.items] == [3, 4]
    assert page.total == 5
    assert page.pages == 3
    assert page.has_next is True
    assert page.has_prev is True


async def test_cursor_pagination_walks_forward(sqlite_db) -> None:
    await _seed()
    p1 = await QuerySet(SqNote).order_by("rank").cursor_paginate(size=2)
    assert [r.rank for r in p1.items] == [1, 2]
    assert p1.has_next is True
    p2 = await QuerySet(SqNote).order_by("rank").cursor_paginate(size=2, after=p1.next_cursor)
    assert [r.rank for r in p2.items] == [3, 4]


async def test_aggregate(sqlite_db) -> None:
    from alchemiq import Avg, Count, Max

    await _seed()
    agg = await QuerySet(SqNote).aggregate(n=Count("id"), top=Max("rank"), mean=Avg("rank"))
    assert agg["n"] == 5
    assert agg["top"] == 5
    assert float(agg["mean"]) == 3.0
