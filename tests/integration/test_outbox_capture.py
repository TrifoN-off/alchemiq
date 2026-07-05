# tests/integration/test_outbox_capture.py
import pytest

from alchemiq import Model, Repository
from alchemiq.outbox import OutboxEvent, connect_outbox
from alchemiq.signals import clear
from alchemiq.types import PK, Maybe, Password, Some

pytestmark = pytest.mark.integration


class OutboxOrder(Model):
    __tablename__ = "outbox_order"
    id: PK[int]
    total: int

    class Meta:
        outbox = True


class OutboxPlain(Model):
    __tablename__ = "outbox_plain"
    id: PK[int]
    name: str


class OutboxDoc(Model):
    __tablename__ = "outbox_doc"
    id: PK[int]
    title: str

    class Meta:
        outbox = True
        soft_delete = True


class OutboxUser(Model):
    __tablename__ = "outbox_user"
    id: PK[int]
    password: Password

    class Meta:
        outbox = True


class OutboxMaybeRow(Model):
    __tablename__ = "outbox_maybe_row"
    id: PK[int]
    note: Maybe[str]

    class Meta:
        outbox = True


@pytest.fixture(autouse=True)
def _outbox_signals():
    clear()
    connect_outbox()
    yield
    clear()


async def _events():
    return await Repository(OutboxEvent).order_by("id").all()


async def test_create_emits_one_created_event(configured_db):
    await Repository(OutboxOrder).create(id=1, total=100)
    evs = await _events()
    assert len(evs) == 1
    ev = evs[0]
    assert ev.topic == "outbox_order.created"
    assert ev.event_type == Some("created")
    assert ev.aggregate_type == Some("outbox_order")
    assert ev.aggregate_id == Some("1")
    assert ev.payload == {"id": 1, "total": 100}
    assert ev.status == "pending"


async def test_update_emits_updated_event(configured_db):
    repo = Repository(OutboxOrder)
    await repo.create(id=2, total=5)
    await repo.update(2, total=9)
    evs = await _events()
    assert [e.event_type for e in evs] == [Some("created"), Some("updated")]
    assert evs[1].topic == "outbox_order.updated"
    assert evs[1].payload == {"id": 2, "total": 9}
    assert evs[1].aggregate_id == Some("2")


async def test_hard_delete_emits_deleted_event(configured_db):
    repo = Repository(OutboxOrder)
    await repo.create(id=3, total=1)
    await repo.delete(3)  # OutboxOrder is not soft-delete -> physical DELETE
    evs = await _events()
    assert [e.event_type for e in evs] == [Some("created"), Some("deleted")]
    assert evs[1].topic == "outbox_order.deleted"
    assert evs[1].payload == {"id": 3, "total": 1}


async def test_soft_delete_then_restore_maps_to_deleted_then_updated(configured_db):
    repo = Repository(OutboxDoc)
    await repo.create(id=1, title="a")
    await repo.delete(1)  # soft-delete -> "deleted"
    await repo.restore(1)  # -> "updated"
    evs = await _events()
    assert [e.event_type for e in evs] == [Some("created"), Some("deleted"), Some("updated")]
    assert evs[1].topic == "outbox_doc.deleted"
    assert evs[2].topic == "outbox_doc.updated"
    assert evs[1].payload["id"] == 1
    assert evs[1].payload["title"] == "a"
    assert evs[1].payload["deleted_at"] is not None  # "deleted" event captured the tombstone
    assert evs[2].payload["deleted_at"] is None  # "updated"/restore cleared the tombstone


async def test_non_outbox_model_emits_nothing(configured_db):
    await Repository(OutboxPlain).create(id=1, name="x")
    assert await Repository(OutboxEvent).all() == []


async def test_password_is_omitted_from_payload(configured_db):
    await Repository(OutboxUser).create(id=1, password="hunter2")
    ev = (await Repository(OutboxEvent).all())[0]
    assert "password" not in ev.payload
    assert "id" in ev.payload


async def test_bulk_create_emits_nothing(configured_db):
    await Repository(OutboxOrder).bulk_create(
        [
            OutboxOrder(id=10, total=1),
            OutboxOrder(id=11, total=2),
        ]
    )
    assert await Repository(OutboxEvent).all() == []


async def test_mass_update_emits_nothing(configured_db):
    repo = Repository(OutboxOrder)
    await repo.create(id=20, total=1)  # per-row create DOES emit one
    before = len(await Repository(OutboxEvent).all())
    await repo.filter(id=20).update(total=99)  # mass set-based UPDATE -> no signal, no event
    after = len(await Repository(OutboxEvent).all())
    assert after == before


async def test_maybe_field_serialized_in_payload(configured_db):
    repo = Repository(OutboxMaybeRow)
    await repo.create(id=1, note="hi")  # Some("hi")
    await repo.create(id=2, note=None)  # Nothing
    evs = await Repository(OutboxEvent).order_by("id").all()
    assert evs[0].payload == {"id": 1, "note": "hi"}
    assert evs[1].payload == {"id": 2, "note": None}
