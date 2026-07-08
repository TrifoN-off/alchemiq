"""Transactional outbox + single-worker relay drain on SQLite."""

from __future__ import annotations

from alchemiq import Repository
from alchemiq.outbox.models import OutboxEvent
from alchemiq.outbox.relay import Relay
from alchemiq.runtime.engine import require_sessionmaker
from tests.sqlite._models import SqOrder


class _Recorder:
    def __init__(self) -> None:
        self.messages: list = []

    async def publish(self, message) -> None:
        self.messages.append(message)


def _sq_events(rows):
    return [r for r in rows if r.topic.startswith("sq_order.")]


async def test_create_writes_outbox_row(sqlite_db) -> None:
    await Repository(SqOrder).create(id=1, total=100)
    events = _sq_events(await Repository(OutboxEvent).all())
    assert len(events) == 1
    assert events[0].topic == "sq_order.created"
    assert events[0].status == "pending"


async def test_relay_drains_and_marks_published(sqlite_db) -> None:
    repo = Repository(SqOrder)
    for i in range(1, 4):
        await repo.create(id=i, total=i * 10)

    pub = _Recorder()
    relay = Relay(pub, batch_size=10)
    drained = await relay._drain_once(require_sessionmaker())

    assert drained >= 3  # at least our three; the claim is table-wide
    events = _sq_events(await Repository(OutboxEvent).all())
    assert all(e.status == "published" for e in events)
    assert len([m for m in pub.messages if m.topic == "sq_order.created"]) == 3
