"""Immutable pagination result containers for offset-based and cursor-based queries."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Generic, TypeVar

M = TypeVar("M")


@dataclass(frozen=True)
class Page(Generic[M]):  # noqa: UP046
    """Offset-based pagination result with total-row metadata."""

    items: list[M]
    total: int
    page: int
    size: int
    pages: int
    has_next: bool
    has_prev: bool

    @classmethod
    def build(cls, items: list[M], total: int, page: int, size: int) -> Page[M]:
        """Construct a ``Page`` from raw query results, computing ``pages`` and nav flags."""
        pages = ceil(total / size) if size else 0
        return cls(
            items=items,
            total=total,
            page=page,
            size=size,
            pages=pages,
            has_next=page < pages,
            has_prev=page > 1,
        )


@dataclass(frozen=True)
class CursorPage(Generic[M]):  # noqa: UP046
    """Keyset/cursor pagination result with opaque forward and backward cursors."""

    items: list[M]
    next_cursor: str | None
    prev_cursor: str | None
    has_next: bool
    has_prev: bool
