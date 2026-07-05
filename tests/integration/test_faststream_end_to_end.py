from __future__ import annotations

import pytest

pytest.importorskip("faststream")  # skip cleanly when the [faststream] extra is absent

from faststream import Depends  # noqa: E402
from faststream.rabbit import RabbitBroker, TestRabbitBroker  # noqa: E402

from alchemiq import Model, Repository  # noqa: E402
from alchemiq.faststream import FastStreamPublisher, unit_of_work  # noqa: E402
from alchemiq.outbox.message import OutboxMessage  # noqa: E402
from alchemiq.outbox.models import OutboxEvent  # noqa: E402
from alchemiq.outbox.relay import Relay  # noqa: E402
from alchemiq.runtime.engine import require_sessionmaker  # noqa: E402
from alchemiq.runtime.session import session_scope  # noqa: E402
from alchemiq.types import PK  # noqa: E402

pytestmark = pytest.mark.integration


class FaststreamOrder(Model):
    __tablename__ = "fstream_order"
    id: PK[int]
    name: str


_broker = RabbitBroker()


@_broker.subscriber("fstream.orders")
async def _consume(evt: dict, uow=Depends(unit_of_work)) -> None:  # noqa: B008
    uow.session.add(FaststreamOrder(id=evt["id"], name=evt["name"]))


def _msg(order_id: int, name: str) -> OutboxMessage:
    return OutboxMessage(
        id=order_id,
        topic="fstream.orders",
        payload={"id": order_id, "name": name},
        headers=None,
        aggregate_type="order",
        aggregate_id=str(order_id),
        event_type="created",
    )


async def test_publish_routes_to_subscriber_and_di_commits(configured_db) -> None:
    # If the row below is missing, fast-depends did NOT honour async-generator teardown
    # (spec §5.4): the injected UnitOfWork never committed. Stop and escalate - the
    # fallback is a per-message middleware that owns the UoW.
    async with TestRabbitBroker(_broker):
        await FastStreamPublisher(_broker).publish(_msg(1, "widget"))
    async with session_scope(write=False) as s:
        row = await s.get(FaststreamOrder, 1)
    assert row is not None
    assert row.name == "widget"


async def test_relay_drains_pending_outbox_to_faststream_subscriber(configured_db) -> None:
    await Repository(OutboxEvent).create(
        topic="fstream.orders", payload={"id": 2, "name": "gadget"}
    )
    async with TestRabbitBroker(_broker):
        relay = Relay(FastStreamPublisher(_broker), batch_size=10)
        drained = await relay._drain_once(require_sessionmaker())
    assert drained == 1
    async with session_scope(write=False) as s:
        row = await s.get(FaststreamOrder, 2)
    assert row is not None
    assert row.name == "gadget"
