from __future__ import annotations

import pytest

from alchemiq.runtime.post_commit import (
    discard_region,
    drain_region,
    enqueue_post_commit,
    open_region,
)

pytestmark = pytest.mark.unit


async def test_drain_runs_callbacks_in_order() -> None:
    ran: list[int] = []
    token = open_region()
    enqueue_post_commit(lambda: _append(ran, 1))
    enqueue_post_commit(lambda: _append(ran, 2))
    assert ran == []  # nothing runs before drain
    await drain_region(token)
    assert ran == [1, 2]


async def test_discard_runs_nothing() -> None:
    ran: list[int] = []
    token = open_region()
    enqueue_post_commit(lambda: _append(ran, 1))
    discard_region(token)
    assert ran == []


async def test_nested_open_returns_none_and_inner_drain_is_noop() -> None:
    ran: list[int] = []
    outer = open_region()
    inner = open_region()  # already active -> None
    assert inner is None
    enqueue_post_commit(lambda: _append(ran, 1))
    await drain_region(inner)  # no-op
    assert ran == []
    await drain_region(outer)
    assert ran == [1]


async def test_failing_callback_does_not_stop_others() -> None:
    ran: list[int] = []
    token = open_region()
    enqueue_post_commit(_boom)
    enqueue_post_commit(lambda: _append(ran, 2))
    await drain_region(token)  # must not raise
    assert ran == [2]


async def test_enqueue_with_no_region_is_noop() -> None:
    enqueue_post_commit(_boom)  # no active region -> dropped, must not raise


def _append(target: list[int], value: int):
    async def cb() -> None:
        target.append(value)

    return cb()


def _boom():
    async def cb() -> None:
        raise RuntimeError("boom")

    return cb()
