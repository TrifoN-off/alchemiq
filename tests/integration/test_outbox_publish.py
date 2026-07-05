import pytest
from pydantic import BaseModel

from alchemiq import OutboxEvent, Repository, UnitOfWork, publish
from alchemiq.outbox.status import PENDING
from alchemiq.types import Nothing, Some

pytestmark = pytest.mark.integration


async def test_publish_stores_one_pending_event(configured_db):
    await publish("user.signed_up", {"id": 1, "email": "a@b.c"})
    rows = await Repository(OutboxEvent).all()
    assert len(rows) == 1
    ev = rows[0]
    assert ev.topic == "user.signed_up"
    assert ev.payload == {"id": 1, "email": "a@b.c"}
    assert ev.status == PENDING
    assert ev.event_type is Nothing
    assert ev.aggregate_type is Nothing


async def test_publish_dumps_basemodel_payload(configured_db):
    class Evt(BaseModel):
        id: int
        name: str

    await publish("user.signed_up", Evt(id=7, name="neo"))
    ev = (await Repository(OutboxEvent).all())[0]
    assert ev.payload == {"id": 7, "name": "neo"}


async def test_publish_key_becomes_aggregate_id(configured_db):
    await publish("billing.upgraded", {"x": 1}, key="42")
    ev = (await Repository(OutboxEvent).all())[0]
    assert ev.aggregate_id == Some("42")


async def test_publish_inside_uow_rolls_back_with_it(configured_db):
    with pytest.raises(RuntimeError, match="boom"):
        async with UnitOfWork():
            await publish("a.b", {"n": 1})
            raise RuntimeError("boom")
    assert await Repository(OutboxEvent).all() == []
