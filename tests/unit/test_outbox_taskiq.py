import json

import pytest

pytest.importorskip("aio_pika")  # skip cleanly when the [outbox] extra is absent

from alchemiq.outbox.message import OutboxMessage  # noqa: E402
from alchemiq.outbox.publisher import TransientPublishError  # noqa: E402
from alchemiq.outbox.taskiq import TaskIQPublisher  # noqa: E402


class _FakeExchange:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.published: list = []

    async def publish(self, message, routing_key):
        if self.error is not None:
            raise self.error
        self.published.append((message, routing_key))


def _msg() -> OutboxMessage:
    return OutboxMessage(
        id=1,
        topic="orders.created",
        payload={"id": 7},
        headers={"trace": "x"},
        aggregate_type="orders",
        aggregate_id="7",
        event_type="created",
    )


async def test_publish_maps_topic_payload_and_headers():
    exchange = _FakeExchange()
    await TaskIQPublisher(exchange).publish(_msg())
    ((amqp_message, routing_key),) = exchange.published
    assert routing_key == "orders.created"
    assert json.loads(amqp_message.body) == {"id": 7}
    assert dict(amqp_message.headers) == {"trace": "x"}


async def test_connection_error_becomes_transient():
    exchange = _FakeExchange(error=ConnectionError("broker down"))
    with pytest.raises(TransientPublishError, match="broker down") as exc_info:
        await TaskIQPublisher(exchange).publish(_msg())
    assert exc_info.value.__cause__ is not None


async def test_non_connection_error_propagates():
    exchange = _FakeExchange(error=ValueError("nope"))
    with pytest.raises(ValueError):
        await TaskIQPublisher(exchange).publish(_msg())
