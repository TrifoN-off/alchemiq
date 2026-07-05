from __future__ import annotations

import pytest

from alchemiq.faststream import FastStreamPublisher
from alchemiq.outbox.message import OutboxMessage
from alchemiq.outbox.publisher import TransientPublishError

pytestmark = pytest.mark.unit


class _FakeBroker:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.published: list = []

    async def publish(self, message, destination, *, headers=None, correlation_id=None):
        if self.error is not None:
            raise self.error
        self.published.append((message, destination, headers, correlation_id))


def _msg() -> OutboxMessage:
    return OutboxMessage(
        id=7,
        topic="orders.created",
        payload={"id": 7},
        headers={"trace": "x"},
        aggregate_type="orders",
        aggregate_id="7",
        event_type="created",
    )


async def test_publish_maps_payload_topic_correlation() -> None:
    broker = _FakeBroker()
    await FastStreamPublisher(broker).publish(_msg())
    ((payload, destination, _headers, correlation_id),) = broker.published
    assert payload == {"id": 7}
    assert destination == "orders.created"
    assert correlation_id == "7"


async def test_publish_enriches_headers_with_event_metadata() -> None:
    broker = _FakeBroker()
    await FastStreamPublisher(broker).publish(_msg())
    ((_payload, _destination, headers, _cid),) = broker.published
    assert headers["trace"] == "x"
    assert headers["alchemiq.aggregate_type"] == "orders"
    assert headers["alchemiq.aggregate_id"] == "7"
    assert headers["alchemiq.event_type"] == "created"


async def test_publish_omits_absent_metadata() -> None:
    broker = _FakeBroker()
    msg = OutboxMessage(
        id=1,
        topic="t",
        payload={},
        headers=None,
        aggregate_type=None,
        aggregate_id=None,
        event_type=None,
    )
    await FastStreamPublisher(broker).publish(msg)
    ((_payload, _destination, headers, _cid),) = broker.published
    assert headers == {}


async def test_connection_error_becomes_transient() -> None:
    broker = _FakeBroker(error=ConnectionError("broker down"))
    with pytest.raises(TransientPublishError, match="broker down") as exc_info:
        await FastStreamPublisher(broker).publish(_msg())
    assert exc_info.value.__cause__ is not None


async def test_custom_transient_error_is_classified() -> None:
    class BrokerGone(Exception):
        pass

    broker = _FakeBroker(error=BrokerGone("gone"))
    with pytest.raises(TransientPublishError):
        await FastStreamPublisher(broker, transient_errors=(BrokerGone,)).publish(_msg())


async def test_non_transient_error_propagates() -> None:
    broker = _FakeBroker(error=ValueError("nope"))
    with pytest.raises(ValueError):
        await FastStreamPublisher(broker).publish(_msg())
