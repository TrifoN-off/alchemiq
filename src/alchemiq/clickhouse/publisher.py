"""ClickHousePublisher: outbox relay adapter that batch-inserts into a CH model."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from alchemiq.clickhouse.repository import _insert_rows
from alchemiq.outbox.message import OutboxMessage

_FIELDS = ("id", "topic", "payload", "headers", "aggregate_type", "aggregate_id", "event_type")


class ClickHousePublisher:
    """Outbox :class:`.Publisher` adapter that batch-inserts messages into a ClickHouse model.

    Used as the ``publisher`` argument to :class:`.Relay` when the outbox relay
    target is a ClickHouse table rather than a message broker.

    E.g.::

        from alchemiq.clickhouse.publisher import ClickHousePublisher
        from alchemiq.outbox.relay import Relay

        publisher = ClickHousePublisher(EventLog)
        relay = Relay(publisher)

    :param target_model: A :class:`.ClickHouseModel` subclass that receives the
        inserted rows.
    :param mapper: Optional callable ``(OutboxMessage) -> dict`` to customise how
        each message is mapped to a row.  When ``None``, the default mapping copies
        the standard outbox fields (``id``, ``topic``, ``payload``, ``headers``,
        ``aggregate_type``, ``aggregate_id``, ``event_type``) that exist on the model.
    """

    def __init__(
        self,
        target_model: type,
        *,
        mapper: Callable[[OutboxMessage], dict[str, Any]] | None = None,
    ) -> None:
        self._model = target_model
        self._mapper = mapper
        self._columns = {c.key for c in target_model.__table__.columns}  # ty: ignore[unresolved-attribute]

    def _to_row(self, message: OutboxMessage) -> dict[str, Any]:
        if self._mapper is not None:
            return self._mapper(message)
        return {f: getattr(message, f) for f in _FIELDS if f in self._columns}

    async def publish(self, message: OutboxMessage) -> None:
        """Insert a single outbox message into the target CH model."""
        await self.publish_batch([message])

    async def publish_batch(self, messages: list[OutboxMessage]) -> None:
        """Map *messages* to target-model rows and bulk-insert them in one CH call."""
        objs = [self._model(**self._to_row(m)) for m in messages]
        await _insert_rows(self._model, objs)
