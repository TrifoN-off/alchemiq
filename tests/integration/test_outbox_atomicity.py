# tests/integration/test_outbox_atomicity.py
import pytest

from alchemiq import Model, Repository, UnitOfWork
from alchemiq.outbox import OutboxEvent, connect_outbox
from alchemiq.signals import clear
from alchemiq.types import PK, Some

pytestmark = pytest.mark.integration


class OutboxAtomicAcct(Model):
    __tablename__ = "outbox_atomic_acct"
    id: PK[int]
    balance: int

    class Meta:
        outbox = True


@pytest.fixture(autouse=True)
def _outbox_signals():
    clear()
    connect_outbox()
    yield
    clear()


async def test_uow_rollback_discards_both_event_and_state(configured_db):
    repo = Repository(OutboxAtomicAcct)
    with pytest.raises(RuntimeError, match="boom"):
        async with UnitOfWork():
            await repo.create(id=1, balance=10)
            raise RuntimeError("boom")
    assert await repo.get_or_none(id=1) is None
    assert await Repository(OutboxEvent).all() == []


async def test_uow_commit_persists_both_event_and_state(configured_db):
    repo = Repository(OutboxAtomicAcct)
    async with UnitOfWork():
        await repo.create(id=2, balance=5)
    assert await repo.get_or_none(id=2) is not None
    evs = await Repository(OutboxEvent).all()
    assert len(evs) == 1
    assert evs[0].aggregate_id == Some("2")
    assert evs[0].topic == "outbox_atomic_acct.created"
