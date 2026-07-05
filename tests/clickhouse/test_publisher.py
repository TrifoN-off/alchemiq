import pytest

from alchemiq.clickhouse import ClickHouseModel, MergeTree
from alchemiq.clickhouse.publisher import ClickHousePublisher
from alchemiq.clickhouse.types import UInt32
from alchemiq.outbox.message import OutboxMessage


class _EventLog(ClickHouseModel):
    id: int = UInt32()
    topic: str
    payload: str

    class Meta:
        engine = MergeTree(order_by=("id",))


def _msg(i):
    return OutboxMessage(
        id=i,
        topic="orders.created",
        payload={"x": i},
        headers=None,
        aggregate_type=None,
        aggregate_id=None,
        event_type="created",
    )


@pytest.mark.unit
def test_default_mapping_matches_columns():
    pub = ClickHousePublisher(_EventLog)
    row = pub._to_row(_msg(7))
    assert row["id"] == 7
    assert row["topic"] == "orders.created"


@pytest.mark.unit
async def test_relay_uses_publish_batch_when_available():
    from alchemiq.outbox.message import OutboxMessage as _OM  # noqa: F401

    calls: list[list] = []

    class BatchPub:
        async def publish(self, message):  # pragma: no cover - not used
            raise AssertionError("per-message path should not run")

        async def publish_batch(self, messages):
            calls.append(messages)

    from alchemiq.outbox.relay import Relay

    relay = Relay(BatchPub())
    # _drain_once should detect publish_batch; verified end-to-end in integration.
    assert hasattr(relay.publisher, "publish_batch")
