"""Low-level helpers for writing OutboxEvent rows within an active session."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from alchemiq.outbox.models import OutboxEvent
from alchemiq.runtime.session import session_scope


def _write_event(
    session: Any,
    *,
    topic: str,
    payload: dict[str, Any],
    aggregate_type: str | None = None,
    aggregate_id: str | None = None,
    event_type: str | None = None,
    headers: dict[str, Any] | None = None,
) -> None:
    session.add(
        OutboxEvent(
            topic=topic,
            payload=payload,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            headers=headers,
        )
    )


async def publish(
    topic: str,
    payload: dict[str, Any] | BaseModel,
    *,
    key: str | None = None,
    headers: dict[str, Any] | None = None,
) -> None:
    """Write an outbox event row in its own autocommit transaction.

    Use this for manual event emission (e.g. from a background task or CLI) when no
    model signal is firing.  To tie the event to a business transaction, open a
    :class:`.UnitOfWork` around the call.

    E.g.::

        from alchemiq import publish

        await publish("user.signed_up", {"id": 1, "email": "ada@x.io"})

        # with a Pydantic payload:
        await publish("billing.upgraded", BillingUpgraded(plan="pro"), key="user-42")

    :param topic: broker routing key (e.g. ``"user.signed_up"``).
    :param payload: event data - a plain ``dict`` or a Pydantic ``BaseModel``.
    :param key: stored as ``aggregate_id``; typically used as the broker partition key.
    :param headers: optional broker-level headers dict.

    .. seealso:: :class:`.Relay` - background worker that picks up and delivers these rows.
    """
    data = payload.model_dump() if isinstance(payload, BaseModel) else dict(payload)
    async with session_scope(write=True) as session:
        _write_event(session, topic=topic, payload=data, aggregate_id=key, headers=headers)
