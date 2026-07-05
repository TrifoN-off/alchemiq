"""OutboxEvent ORM model and related utilities."""

from __future__ import annotations

from alchemiq.model import Model
from alchemiq.model.meta_options import Index
from alchemiq.outbox.status import PENDING
from alchemiq.types import JSON, PK, CreatedAt, DateTimeTz, Maybe


class OutboxEvent(Model):
    """Persistent outbox row storing a domain event awaiting broker delivery.

    Status lifecycle: ``pending`` -> ``published`` (success) or ``failed`` (delivery
    error, retryable) -> ``dead`` (``max_attempts`` reached).

    .. seealso:: :class:`.Relay` - background worker that drains this table.
    """

    id: PK[int]
    topic: str
    aggregate_type: Maybe[str]
    aggregate_id: Maybe[str]
    event_type: Maybe[str]
    payload: JSON
    headers: Maybe[JSON]
    status: str = PENDING
    attempts: int = 0
    created_at: CreatedAt
    published_at: Maybe[DateTimeTz]
    last_error: Maybe[str]

    class Meta:
        """Maps to the ``outbox`` table with a ``(status, id)`` index for efficient polling."""

        table_name = "outbox"
        indexes = (Index("status", "id"),)


def is_outbox(model: type) -> bool:
    """Return ``True`` if the model has ``Meta.outbox = True``."""
    meta = getattr(model, "__alchemiq_meta__", None)
    return bool(meta and meta.outbox)
