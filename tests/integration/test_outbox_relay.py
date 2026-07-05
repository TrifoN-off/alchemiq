import pytest

from alchemiq import Repository
from alchemiq.outbox.models import OutboxEvent
from alchemiq.outbox.relay import Relay
from alchemiq.runtime.engine import require_sessionmaker

pytestmark = pytest.mark.integration


class _Recorder:
    def __init__(self) -> None:
        self.messages: list = []

    async def publish(self, message) -> None:
        self.messages.append(message)


async def test_drain_publishes_all_pending_in_id_order_and_marks_published(configured_db):
    repo = Repository(OutboxEvent)
    for i in range(3):
        await repo.create(topic="orders.created", payload={"i": i})

    pub = _Recorder()
    relay = Relay(pub, batch_size=10)
    drained = await relay._drain_once(require_sessionmaker())

    assert drained == 3
    assert [m.payload["i"] for m in pub.messages] == [0, 1, 2]
    rows = sorted(await repo.all(), key=lambda e: e.id)
    assert [r.status for r in rows] == ["published", "published", "published"]
    assert all(r.published_at.is_some for r in rows)


async def test_claim_ignores_published_and_dead_rows(configured_db):
    repo = Repository(OutboxEvent)
    await repo.create(topic="t.created", payload={"k": "pending"})
    await repo.create(topic="t.created", payload={"k": "done"}, status="published")
    await repo.create(topic="t.created", payload={"k": "gone"}, status="dead")

    pub = _Recorder()
    relay = Relay(pub, batch_size=10)
    drained = await relay._drain_once(require_sessionmaker())

    assert drained == 1
    assert [m.payload["k"] for m in pub.messages] == ["pending"]
