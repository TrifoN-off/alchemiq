from dataclasses import FrozenInstanceError

import pytest

from alchemiq.repository.pagination import Page


def test_page_math_middle():
    p = Page.build(items=[1, 2], total=10, page=2, size=2)
    assert p.pages == 5
    assert p.has_prev is True
    assert p.has_next is True


def test_page_math_last():
    p = Page.build(items=[9, 10], total=10, page=5, size=2)
    assert p.has_next is False
    assert p.has_prev is True


def test_page_math_first_and_only():
    p = Page.build(items=[1], total=1, page=1, size=20)
    assert p.pages == 1
    assert p.has_next is False
    assert p.has_prev is False


def test_page_is_frozen():
    p = Page.build(items=[], total=0, page=1, size=20)
    with pytest.raises(FrozenInstanceError):
        p.total = 5  # type: ignore[misc]


async def test_paginate_size_zero_raises():
    # The guard `if page < 1 or size < 1` fires before `await self.count()`,
    # so this needs no engine/Docker.
    from alchemiq import Model
    from alchemiq.query import QuerySet
    from alchemiq.types import PK

    class PgSizeRow(Model):
        __tablename__ = "page_unit_pg_size_row"
        id: PK[int]

    with pytest.raises(ValueError):
        await QuerySet(PgSizeRow).paginate(page=1, size=0)
