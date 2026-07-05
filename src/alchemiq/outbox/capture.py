"""Signal handlers that write outbox rows on post_create/post_update/post_delete.

Capture fires from alchemiq signals, not from bulk operations (insert/update_many/delete_many).
Only models with ``Meta.outbox = True`` produce outbox rows.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import object_session

from alchemiq.outbox.models import is_outbox
from alchemiq.outbox.store import _write_event
from alchemiq.query.queryset import pk_name
from alchemiq.signals.registry import connect, disconnect


def _capture(instance: Any, event_type: str) -> None:
    model = type(instance)
    if not is_outbox(model):
        return
    table = instance.__tablename__
    _write_event(
        object_session(instance),
        topic=f"{table}.{event_type}",
        payload=instance.to_dict(mode="json"),
        aggregate_type=table,
        aggregate_id=str(getattr(instance, pk_name(model))),
        event_type=event_type,
    )


async def _on_create(instance: Any, **_: Any) -> None:
    _capture(instance, "created")


async def _on_update(instance: Any, **_: Any) -> None:
    _capture(instance, "updated")


async def _on_delete(instance: Any, **_: Any) -> None:
    _capture(instance, "deleted")


_HANDLERS = (
    ("post_create", _on_create),
    ("post_update", _on_update),
    ("post_delete", _on_delete),
)


def connect_outbox() -> None:
    """Register post_create/post_update/post_delete signal handlers that write outbox rows.

    Safe to call multiple times; existing registrations are removed first.
    """
    for event, handler in _HANDLERS:
        disconnect(handler, sender=None, event=event)
        connect(handler, sender=None, event=event)
