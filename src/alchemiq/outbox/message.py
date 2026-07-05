"""Broker-agnostic message value object produced from an OutboxEvent row."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from alchemiq.types import Maybe


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    """Immutable, broker-agnostic view of one outbox row handed to a :class:`.Publisher`.

    Produced from an :class:`.OutboxEvent` row by the :class:`.Relay` before each
    delivery attempt.  Consumers should deduplicate on ``id``.
    """

    id: int
    topic: str
    payload: dict[str, Any]
    headers: dict[str, Any] | None
    aggregate_type: str | None
    aggregate_id: str | None
    event_type: str | None


def _unwrap(value: Any) -> Any:
    """Unwrap a Maybe[T] to its value or None; pass any non-Maybe value through unchanged."""
    if isinstance(value, Maybe):
        return value.unwrap_or(None)
    return value


def to_message(row: Any) -> OutboxMessage:
    """Convert an ``OutboxEvent`` ORM row to an ``OutboxMessage`` value object."""
    # row is an OutboxEvent; typed Any to sidestep the annotation-first static-typing wart.
    return OutboxMessage(
        id=row.id,
        topic=row.topic,
        payload=row.payload,
        headers=_unwrap(row.headers),
        aggregate_type=_unwrap(row.aggregate_type),
        aggregate_id=_unwrap(row.aggregate_id),
        event_type=_unwrap(row.event_type),
    )
