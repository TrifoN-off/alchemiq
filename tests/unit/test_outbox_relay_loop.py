import asyncio

import pytest

from alchemiq.outbox.publisher import TransientPublishError
from alchemiq.outbox.relay import Relay


class _NullPublisher:
    async def publish(self, message) -> None: ...


def _patch(relay, monkeypatch, drain):
    waits: list[float] = []

    async def fake_wait(timeout: float) -> None:
        waits.append(timeout)

    monkeypatch.setattr(relay, "_drain_once", drain)
    monkeypatch.setattr(relay, "_wait", fake_wait)
    monkeypatch.setattr("alchemiq.outbox.relay.require_sessionmaker", lambda: object())
    return waits


async def test_full_batch_does_not_wait(monkeypatch):
    relay = Relay(_NullPublisher(), batch_size=2, poll_interval=1.0)
    calls = {"n": 0}

    async def drain(_sm) -> int:
        calls["n"] += 1
        if calls["n"] >= 2:
            relay.stop()
        return relay.batch_size  # always a full batch

    waits = _patch(relay, monkeypatch, drain)
    await relay.run()
    assert waits == []


async def test_partial_batch_waits_poll_interval(monkeypatch):
    relay = Relay(_NullPublisher(), batch_size=2, poll_interval=1.0)
    calls = {"n": 0}

    async def drain(_sm) -> int:
        calls["n"] += 1
        if calls["n"] == 1:
            return 1  # partial -> should wait poll_interval
        relay.stop()
        return relay.batch_size

    waits = _patch(relay, monkeypatch, drain)
    await relay.run()
    assert waits == [1.0]


async def test_transient_error_waits_error_backoff(monkeypatch):
    relay = Relay(_NullPublisher(), batch_size=2, poll_interval=1.0, error_backoff=5.0)
    calls = {"n": 0}

    async def drain(_sm) -> int:
        calls["n"] += 1
        if calls["n"] == 1:
            raise TransientPublishError("down")
        relay.stop()
        return relay.batch_size

    waits = _patch(relay, monkeypatch, drain)
    await relay.run()
    assert waits == [5.0]


async def test_stop_before_run_executes_no_cycles(monkeypatch):
    relay = Relay(_NullPublisher(), batch_size=2)
    calls = {"n": 0}

    async def drain(_sm) -> int:
        calls["n"] += 1
        return 0

    _patch(relay, monkeypatch, drain)
    relay.stop()
    await relay.run()
    assert calls["n"] == 0


async def test_real_wait_times_out():
    # Exercises the real _wait body: asyncio.wait_for + except TimeoutError.
    # Stopping event is never set, so wait_for raises TimeoutError which _wait catches.
    relay = Relay(_NullPublisher(), batch_size=2)
    await relay._wait(0.01)  # should return after ~10ms without raising
    assert not relay._stopping.is_set()


async def test_run_cancelled_sets_stopping(monkeypatch):
    # Exercises the except asyncio.CancelledError branch in run().
    relay = Relay(_NullPublisher(), batch_size=2)

    async def slow_drain(_sm) -> int:
        await asyncio.sleep(10)
        return 0

    monkeypatch.setattr(relay, "_drain_once", slow_drain)
    monkeypatch.setattr(relay, "_wait", lambda timeout: asyncio.sleep(0))
    monkeypatch.setattr("alchemiq.outbox.relay.require_sessionmaker", lambda: object())

    task = asyncio.create_task(relay.run())
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert relay._stopping.is_set()
