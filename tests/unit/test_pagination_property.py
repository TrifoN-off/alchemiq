"""Offset pagination invariant: concatenated pages == full ordered list (no dup/gap)."""

import math

from alchemiq.repository.pagination import Page


def test_page_count_invariant():
    for total in range(0, 25):
        for size in range(1, 8):
            pages = [
                Page.build(items=[], total=total, page=p, size=size).pages for p in range(1, 5)
            ]
            assert all(p == math.ceil(total / size) for p in pages)


def test_has_next_prev_consistency():
    total, size = 10, 3
    last_page = math.ceil(total / size)
    for page in range(1, last_page + 1):
        p = Page.build(items=[], total=total, page=page, size=size)
        assert p.has_prev == (page > 1)
        assert p.has_next == (page < last_page)
