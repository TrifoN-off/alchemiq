import asyncio

import pytest

from alchemiq.clickhouse import ClickHouseModel, ClickHouseRepository, MergeTree
from alchemiq.clickhouse.repository import BufferedInserter
from alchemiq.clickhouse.types import UInt32
from alchemiq.exceptions import ClickHouseError


class _Buf(ClickHouseModel):
    id: int = UInt32()

    class Meta:
        engine = MergeTree(order_by=("id",))


class _RecordingRepo(ClickHouseRepository[_Buf]):
    def __init__(self):
        super().__init__()
        self.flushed: list[list] = []
        self.fail_next = False

    async def bulk_insert(self, objs):
        items = list(objs)
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("boom")
        self.flushed.append(items)
        return items


@pytest.mark.unit
async def test_size_trigger_flush():
    repo = _RecordingRepo()
    buf = BufferedInserter(repo, max_rows=2, flush_interval=999)
    await buf.add(_Buf(id=1))
    assert repo.flushed == []  # below threshold
    await buf.add(_Buf(id=2))  # hits max_rows -> flush
    assert len(repo.flushed) == 1 and len(repo.flushed[0]) == 2
    await buf.close()


@pytest.mark.unit
async def test_failure_retains_rows():
    repo = _RecordingRepo()
    buf = BufferedInserter(repo, max_rows=1, flush_interval=999)
    repo.fail_next = True
    await buf.add(_Buf(id=1))  # flush raises internally -> rows retained
    assert repo.flushed == []
    await buf.flush()  # retry succeeds
    assert len(repo.flushed) == 1
    await buf.close()


@pytest.mark.unit
async def test_max_buffered_backpressure():
    repo = _RecordingRepo()
    buf = BufferedInserter(repo, max_rows=999, flush_interval=999, max_buffered=1)
    await buf.add(_Buf(id=1))
    with pytest.raises(ClickHouseError):
        await buf.add(_Buf(id=2))
    await buf.close()


@pytest.mark.unit
async def test_context_manager_drains_on_exit():
    repo = _RecordingRepo()
    async with repo.buffered(max_rows=999, flush_interval=999) as buf:
        await buf.add(_Buf(id=1))
    assert len(repo.flushed) == 1


@pytest.mark.unit
async def test_cancelled_timer_still_flushes_on_close():
    repo = _RecordingRepo()
    buf = BufferedInserter(repo, max_rows=999, flush_interval=999)
    await buf.add(_Buf(id=1))  # starts the timer; row stays buffered (below max_rows)
    assert repo.flushed == []
    # give the timer task one tick to actually start running before cancelling
    await asyncio.sleep(0)
    buf._timer.cancel()
    await buf.close()  # must still flush the buffered row despite cancelled timer
    assert repo.flushed and repo.flushed[-1][0].id == 1


@pytest.mark.unit
async def test_add_many_buffers_and_flushes():
    repo = _RecordingRepo()
    buf = BufferedInserter(repo, max_rows=999, flush_interval=999)
    await buf.add_many([_Buf(id=1), _Buf(id=2), _Buf(id=3)])
    assert repo.flushed == []  # still below max_rows
    await buf.close()  # close flushes everything
    assert len(repo.flushed) == 1
    assert [r.id for r in repo.flushed[0]] == [1, 2, 3]


@pytest.mark.clickhouse
async def test_timer_flush_round_trip(configured_clickhouse):
    repo = ClickHouseRepository(_Buf)
    async with repo.buffered(max_rows=999, flush_interval=0.2) as buf:
        await buf.add(_Buf(id=1))
        await asyncio.sleep(0.5)  # timer flushes
    rows = await repo.order_by("id").all()
    assert [r.id for r in rows] == [1]
