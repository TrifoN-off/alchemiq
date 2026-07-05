"""Post-commit region: queue async callbacks that run after the outermost transaction commits."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token

logger = logging.getLogger("alchemiq.cache")

PostCommitCallback = Callable[[], Awaitable[None]]

_region: ContextVar[list[PostCommitCallback] | None] = ContextVar(
    "alchemiq_post_commit", default=None
)


def open_region() -> Token[list[PostCommitCallback] | None] | None:
    """Open a post-commit region if none is active. Returns a token to drain it, or None."""
    if _region.get() is not None:
        return None
    return _region.set([])


def enqueue_post_commit(cb: PostCommitCallback) -> None:
    """Queue a callback to run after the active transaction commits."""
    region = _region.get()
    if region is None:
        logger.debug("enqueue_post_commit called with no active region; dropping callback")
        return
    region.append(cb)


async def drain_region(token: Token[list[PostCommitCallback] | None] | None) -> None:
    """Run and clear the region's callbacks (fail-open per callback). No-op if token is None."""
    if token is None:
        return
    region = _region.get()
    _region.reset(token)
    if not region:
        return
    for cb in region:
        try:
            await cb()
        except Exception:  # noqa: BLE001 - a failed invalidation must not break a committed txn
            logger.warning("post-commit callback failed", exc_info=True)


def discard_region(token: Token[list[PostCommitCallback] | None] | None) -> None:
    """Drop the region's callbacks without running them (rollback path). No-op if token is None."""
    if token is not None:
        _region.reset(token)
