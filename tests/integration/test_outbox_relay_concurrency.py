import pytest

from alchemiq import Repository
from alchemiq.outbox.models import OutboxEvent
from alchemiq.outbox.relay import Relay
from alchemiq.runtime.engine import require_sessionmaker

pytestmark = pytest.mark.integration


class _NullPublisher:
    async def publish(self, message) -> None: ...


async def test_skip_locked_gives_two_claimers_disjoint_rows(configured_db):
    repo = Repository(OutboxEvent)
    for i in range(4):
        await repo.create(topic="t.created", payload={"i": i})

    sm = require_sessionmaker()
    relay = Relay(_NullPublisher(), batch_size=2)

    async with sm() as s1, s1.begin():
        rows1 = (await s1.execute(relay._claim_stmt())).scalars().all()
        async with sm() as s2, s2.begin():
            rows2 = (await s2.execute(relay._claim_stmt())).scalars().all()
            ids1 = {r.id for r in rows1}
            ids2 = {r.id for r in rows2}

    assert len(ids1) == 2
    assert len(ids2) == 2
    assert ids1.isdisjoint(ids2)
