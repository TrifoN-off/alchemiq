# tests/integration/test_outbox_relay_failures.py
import pytest

from alchemiq import Repository
from alchemiq.outbox.models import OutboxEvent
from alchemiq.outbox.publisher import TransientPublishError
from alchemiq.outbox.relay import Relay
from alchemiq.outbox.status import DEAD, FAILED, PENDING, PUBLISHED
from alchemiq.runtime.engine import require_sessionmaker
from alchemiq.types import Nothing, Some

pytestmark = pytest.mark.integration


class _AlwaysPoison:
    async def publish(self, message) -> None:
        raise RuntimeError("bad payload")


class _TransientAfterFirst:
    def __init__(self) -> None:
        self.calls = 0

    async def publish(self, message) -> None:
        self.calls += 1
        if self.calls == 1:
            return
        raise TransientPublishError("broker down")


class _BatchRecorder:
    """Fake publisher that records every publish_batch call - no per-message path."""

    def __init__(self) -> None:
        self.batch_calls: list[list] = []

    async def publish(self, message) -> None:  # pragma: no cover
        raise AssertionError("per-message path must not run when publish_batch is present")

    async def publish_batch(self, messages) -> None:
        self.batch_calls.append(list(messages))


class _BatchPoison:
    """Fake publisher whose publish_batch always raises a non-transient error."""

    async def publish(self, message) -> None:  # pragma: no cover
        raise AssertionError("per-message path must not run when publish_batch is present")

    async def publish_batch(self, messages) -> None:
        raise RuntimeError("batch rejected")


class _BatchTransient:
    """Fake publisher whose publish_batch always raises TransientPublishError."""

    async def publish(self, message) -> None:  # pragma: no cover
        raise AssertionError("per-message path must not run when publish_batch is present")

    async def publish_batch(self, messages) -> None:
        raise TransientPublishError("broker down")


async def test_poison_marks_failed_then_dead(configured_db):
    repo = Repository(OutboxEvent)
    await repo.create(topic="x.created", payload={})
    relay = Relay(_AlwaysPoison(), batch_size=10, max_attempts=2)

    await relay._drain_once(require_sessionmaker())
    row = (await repo.all())[0]
    assert row.status == "failed"
    assert row.attempts == 1
    assert row.last_error == Some("bad payload")

    await relay._drain_once(require_sessionmaker())
    row = (await repo.all())[0]
    assert row.status == "dead"
    assert row.attempts == 2
    assert row.last_error == Some("bad payload")


async def test_transient_error_rolls_back_whole_batch(configured_db):
    repo = Repository(OutboxEvent)
    await repo.create(topic="a.created", payload={"n": 1})
    await repo.create(topic="b.created", payload={"n": 2})
    relay = Relay(_TransientAfterFirst(), batch_size=10)

    with pytest.raises(TransientPublishError):
        await relay._drain_once(require_sessionmaker())

    rows = sorted(await repo.all(), key=lambda e: e.id)
    assert [r.status for r in rows] == ["pending", "pending"]
    assert all(r.attempts == 0 for r in rows)
    assert all(r.published_at is Nothing for r in rows)


# ---------------------------------------------------------------------------
# Batch-path tests (publisher has publish_batch; relay must NOT call publish)
# ---------------------------------------------------------------------------


async def test_batch_success_marks_all_published(configured_db):
    repo = Repository(OutboxEvent)
    await repo.create(topic="x.created", payload={"n": 1})
    await repo.create(topic="x.created", payload={"n": 2})
    await repo.create(topic="x.created", payload={"n": 3})

    recorder = _BatchRecorder()
    relay = Relay(recorder, batch_size=10)

    count = await relay._drain_once(require_sessionmaker())

    # relay took the batch path and called publish_batch exactly once
    assert count == 3
    assert len(recorder.batch_calls) == 1
    assert len(recorder.batch_calls[0]) == 3

    rows = sorted(await repo.all(), key=lambda e: e.id)
    assert all(r.status == PUBLISHED for r in rows)
    assert all(r.published_at is not Nothing for r in rows)


async def test_batch_poison_marks_failed_then_dead(configured_db):
    repo = Repository(OutboxEvent)
    await repo.create(topic="x.created", payload={})
    relay = Relay(_BatchPoison(), batch_size=10, max_attempts=2)

    await relay._drain_once(require_sessionmaker())
    row = (await repo.all())[0]
    assert row.status == FAILED
    assert row.attempts == 1
    assert row.last_error == Some("batch rejected")

    await relay._drain_once(require_sessionmaker())
    row = (await repo.all())[0]
    assert row.status == DEAD
    assert row.attempts == 2
    assert row.last_error == Some("batch rejected")


async def test_batch_transient_rolls_back_whole_batch(configured_db):
    repo = Repository(OutboxEvent)
    await repo.create(topic="a.created", payload={"n": 1})
    await repo.create(topic="b.created", payload={"n": 2})
    relay = Relay(_BatchTransient(), batch_size=10)

    with pytest.raises(TransientPublishError):
        await relay._drain_once(require_sessionmaker())

    rows = sorted(await repo.all(), key=lambda e: e.id)
    assert [r.status for r in rows] == [PENDING, PENDING]
    assert all(r.attempts == 0 for r in rows)
    assert all(r.published_at is Nothing for r in rows)
