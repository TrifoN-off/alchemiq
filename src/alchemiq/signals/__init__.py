"""Lifecycle event decorators for model create/update/delete.

This package exposes six decorators - :func:`pre_create`, :func:`post_create`,
:func:`pre_update`, :func:`post_update`, :func:`pre_delete`, :func:`post_delete` -
that register an async handler to run around a row's lifecycle.  Each decorator
takes an optional *sender* model class; passing ``None`` (or calling it bare)
registers a global handler that matches every model.

Handlers run **within the same database transaction** that triggered the event,
so raising from a handler rolls back the write.  Per-row signals fire only for
single-row :class:`.Repository` operations; bulk/mass operations
(``bulk_create``, ``filter().update()``, ``filter().delete()``) fire nothing.
For a given event, exact-sender handlers run first, then global handlers, each
in registration order.

E.g.::

    from alchemiq.signals import post_create

    @post_create(User)
    async def on_create(instance, **kw):
        # fires after the INSERT flush, inside the creating transaction;
        # instance.id is assigned and the row is visible within the txn
        seen.append(instance.id)

    await Repository(User).create(id=1, name="a")  # on_create runs with id == 1

Register and remove handlers imperatively with :func:`connect` /
:func:`disconnect`, and drop every registration with :func:`clear` (handy in
test teardown).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from alchemiq.signals.registry import clear, connect, disconnect, dispatch

Handler = Callable[..., Awaitable[None]]
_Decorator = Callable[[Handler], Handler]


def _make(event: str) -> Callable[[type | None], _Decorator]:
    def decorator(sender: type | None = None) -> _Decorator:
        def register(handler: Handler) -> Handler:
            connect(handler, sender=sender, event=event)
            return handler

        return register

    return decorator


pre_create = _make("pre_create")
post_create = _make("post_create")
pre_update = _make("pre_update")
post_update = _make("post_update")
pre_delete = _make("pre_delete")
post_delete = _make("post_delete")

__all__ = [
    "pre_create",
    "post_create",
    "pre_update",
    "post_update",
    "pre_delete",
    "post_delete",
    "connect",
    "disconnect",
    "clear",
    "dispatch",
    "Handler",
]
