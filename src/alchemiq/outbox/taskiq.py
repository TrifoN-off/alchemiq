"""RabbitMQ publisher adapter using aio-pika (taskiq-aio-pika transport)."""

from __future__ import annotations

import json
from typing import Any

import aio_pika  # ty: ignore[unresolved-import]
from aio_pika.exceptions import AMQPConnectionError  # ty: ignore[unresolved-import]

from alchemiq.outbox.message import OutboxMessage
from alchemiq.outbox.publisher import TransientPublishError


class TaskIQPublisher:
    """Publish OutboxMessages to a RabbitMQ exchange (aio-pika, the taskiq-aio-pika transport).

    ``exchange`` is an aio-pika exchange (or any object exposing
    ``async publish(message, routing_key=...)``). The caller owns the broker's
    connection lifecycle (declare/connect/close).
    """

    def __init__(self, exchange: Any) -> None:
        self._exchange = exchange

    async def publish(self, message: OutboxMessage) -> None:
        """Publish one message to the exchange, routing by ``message.topic``.

        Raises ``TransientPublishError`` for AMQP/connection failures so the relay
        backs off without burning the row's attempt counter.
        """
        amqp_message = aio_pika.Message(
            body=json.dumps(message.payload).encode(),
            headers=message.headers,
            content_type="application/json",
        )
        try:
            await self._exchange.publish(amqp_message, routing_key=message.topic)
        except (AMQPConnectionError, ConnectionError, OSError) as e:
            raise TransientPublishError(str(e)) from e
