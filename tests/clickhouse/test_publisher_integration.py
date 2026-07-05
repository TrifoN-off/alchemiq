import pytest

from alchemiq.clickhouse import ClickHouseModel, ClickHouseRepository, MergeTree
from alchemiq.clickhouse.publisher import ClickHousePublisher
from alchemiq.clickhouse.types import UInt32
from alchemiq.outbox.message import OutboxMessage


class _Sink(ClickHouseModel):
    id: int = UInt32()
    topic: str

    class Meta:
        engine = MergeTree(order_by=("id",))


@pytest.mark.clickhouse
async def test_publish_batch_inserts_rows(configured_clickhouse):
    pub = ClickHousePublisher(_Sink)
    await pub.publish_batch(
        [
            OutboxMessage(
                id=1,
                topic="a",
                payload={},
                headers=None,
                aggregate_type=None,
                aggregate_id=None,
                event_type=None,
            ),
            OutboxMessage(
                id=2,
                topic="b",
                payload={},
                headers=None,
                aggregate_type=None,
                aggregate_id=None,
                event_type=None,
            ),
        ]
    )
    rows = await ClickHouseRepository(_Sink).order_by("id").all()
    assert [(r.id, r.topic) for r in rows] == [(1, "a"), (2, "b")]
