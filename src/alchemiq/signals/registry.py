"""Signal handler registry: connect, disconnect, clear, and dispatch by event + sender."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

Handler = Callable[..., Awaitable[None]]

_HANDLERS: dict[tuple[str, type | None], list[Handler]] = {}


def connect(handler: Handler, *, sender: type | None, event: str) -> None:
    """Register *handler* for *event*, optionally scoped to a specific *sender* model."""
    _HANDLERS.setdefault((event, sender), []).append(handler)


def disconnect(handler: Handler, *, sender: type | None, event: str) -> None:
    """Remove *handler* from the *event*/*sender* bucket; silently no-ops if not registered."""
    bucket = _HANDLERS.get((event, sender))
    if bucket and handler in bucket:
        bucket.remove(handler)


def clear() -> None:
    """Remove all registered handlers (useful in test teardown)."""
    _HANDLERS.clear()


async def dispatch(event: str, model: type, instance: Any) -> None:
    """Run exact-model handlers then global handlers, sequentially, in registration order."""
    for sender in (model, None):
        # Iterate a copy: a handler may disconnect/clear during dispatch.
        for handler in list(_HANDLERS.get((event, sender), ())):
            # v1 passes only `instance`; handlers' **kwargs is reserved
            # for forward-compat.
            await handler(instance)
