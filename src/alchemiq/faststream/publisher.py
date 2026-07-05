"""FastStream ``Publisher`` adapter for the alchemiq outbox relay."""

from __future__ import annotations

from typing import Any

from alchemiq.outbox.message import OutboxMessage
from alchemiq.outbox.publisher import TransientPublishError

_DEFAULT_TRANSIENT: tuple[type[Exception], ...] = (ConnectionError, OSError, TimeoutError)


class FastStreamPublisher:
    """Publish ``OutboxMessage`` objects to any FastStream broker.

    Implements the :class:`.Publisher` protocol so it can be wired directly into a
    :class:`.Relay`.  Works with any FastStream broker (RabbitMQ, Kafka, NATS, Redis)
    or any object that exposes the same duck-typed ``publish`` signature::

        async def publish(message, destination, *, headers, correlation_id) -> None: ...

    The caller owns the broker's connection lifecycle (``connect`` / ``start`` /
    ``stop`` / ``close``).  ``correlation_id`` is set to ``str(message.id)`` - the
    dedup key consumers use under the at-least-once delivery contract.

    Connection-class errors (the ``transient_errors`` tuple) are re-raised as
    :class:`.TransientPublishError` so the relay backs off without burning retry
    attempts.  Pass broker-specific connection exception classes in
    ``transient_errors`` without importing them in this module.

    E.g.::

        from faststream.rabbit import RabbitBroker
        from alchemiq.faststream import FastStreamPublisher
        from alchemiq import Relay

        _broker = RabbitBroker()
        relay = Relay(FastStreamPublisher(_broker), batch_size=10)

        # custom transient errors:
        publisher = FastStreamPublisher(_broker, transient_errors=(BrokerGone,))

    :param broker: a started FastStream broker or duck-typed equivalent.
    :param transient_errors: exception classes that indicate a transient connection
        failure and should be wrapped in :class:`.TransientPublishError`;
        defaults to ``(ConnectionError, OSError, TimeoutError)``.

    .. seealso:: :class:`.Relay` - drives the outbox drain loop using this publisher.
    """

    def __init__(
        self,
        broker: Any,
        *,
        transient_errors: tuple[type[Exception], ...] = _DEFAULT_TRANSIENT,
    ) -> None:
        self._broker = broker
        self._transient_errors = transient_errors

    async def publish(self, message: OutboxMessage) -> None:
        """Publish *message* to its ``topic`` via the broker.

        Sets ``correlation_id`` to ``str(message.id)`` and forwards all
        ``alchemiq.*`` metadata headers present on the message.  Re-raises
        connection-class exceptions as :class:`.TransientPublishError` so the
        relay backs off without burning retry attempts.

        :param message: the ``OutboxMessage`` to deliver.
        :raises TransientPublishError: on connection-class errors listed in
            ``transient_errors``.
        """
        try:
            await self._broker.publish(
                message.payload,
                message.topic,
                headers=self._headers(message),
                correlation_id=str(message.id),
            )
        except self._transient_errors as e:
            raise TransientPublishError(str(e)) from e

    @staticmethod
    def _headers(message: OutboxMessage) -> dict[str, Any]:
        headers = dict(message.headers or {})
        for key, value in (
            ("alchemiq.aggregate_type", message.aggregate_type),
            ("alchemiq.aggregate_id", message.aggregate_id),
            ("alchemiq.event_type", message.event_type),
        ):
            if value is not None:
                headers[key] = value
        return headers
