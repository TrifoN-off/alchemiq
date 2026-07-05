"""Publisher protocol and error hierarchy for outbox delivery adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from alchemiq.outbox.message import OutboxMessage  # ty: ignore[unresolved-import]


class PublishError(Exception):
    """Base exception for publisher delivery errors."""


class TransientPublishError(PublishError):
    """Broker unreachable or connection lost.

    When raised by a :class:`.Publisher`, the :class:`.Relay` rolls back the whole
    batch without incrementing ``attempts`` and sleeps ``error_backoff`` seconds before
    retrying.  Use this for temporary infrastructure failures, not logical errors.
    """


@runtime_checkable
class Publisher(Protocol):
    """Structural protocol for outbox delivery adapters.

    Implementations must expose ``publish(message)``.  An optional ``publish_batch(messages)``
    method is detected by duck-typing when present; it is **not** part of this protocol contract,
    so any object with just ``publish`` satisfies ``isinstance(obj, Publisher)``.

    E.g.::

        from alchemiq.outbox import Publisher, TransientPublishError
        from alchemiq.outbox.message import OutboxMessage

        class MyBrokerPublisher:
            async def publish(self, message: OutboxMessage) -> None:
                try:
                    await broker.send(message.topic, message.payload)
                except BrokerConnectionError as e:
                    raise TransientPublishError(str(e)) from e

    .. seealso:: :class:`.Relay` - background loop that calls this protocol.
    """

    async def publish(self, message: OutboxMessage) -> None:
        """Deliver a single message to the broker.

        Raise :class:`.TransientPublishError` for connection failures; the relay backs off
        without incrementing ``attempts``.  Raise any other exception to poison the row
        (increment ``attempts``; mark ``failed`` or ``dead``).

        :param message: the outbox row projected to a broker-agnostic value object.
        :raises TransientPublishError: for transient broker connection failures.
        """
        ...


# publish_batch is an OPTIONAL capability detected by duck-typing (hasattr).
# It is NOT part of the Protocol contract, so any object with just `publish`
# satisfies isinstance(obj, Publisher).
