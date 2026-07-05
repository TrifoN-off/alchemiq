"""Background relay that drains pending and failed outbox rows and delivers them to a broker."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alchemiq.outbox.message import to_message
from alchemiq.outbox.models import OutboxEvent
from alchemiq.outbox.publisher import Publisher, TransientPublishError
from alchemiq.outbox.status import DEAD, FAILED, PENDING, PUBLISHED
from alchemiq.runtime.engine import require_sessionmaker


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Relay:
    """Background relay that drains the outbox table and delivers rows to a broker.

    Each cycle claims a batch with ``FOR UPDATE SKIP LOCKED`` (safe for multiple concurrent
    relay workers), publishes each row, and records the outcome within the same transaction.
    Both ``pending`` and ``failed`` rows are claimed and re-attempted every cycle until they
    reach ``dead``.

    Delivery semantics: **at-least-once** - consumers must deduplicate on
    ``OutboxMessage.id``.

    Error taxonomy:

    - :class:`.TransientPublishError` -> whole-batch rollback; ``attempts`` is **not**
      incremented; relay sleeps ``error_backoff`` seconds before the next cycle.
    - Any other exception (per-message path) -> per-event poison: ``attempts`` incremented;
      status set to ``failed`` or ``dead`` (when ``attempts >= max_attempts``).
    - Any other exception (``publish_batch`` path) -> whole-batch poison: all rows in the
      claimed batch are poisoned together (not row-by-row).

    E.g.::

        import asyncio
        from alchemiq.outbox import Relay

        relay = Relay(my_publisher, batch_size=50, poll_interval=2.0, max_attempts=5)

        # run in a background task:
        task = asyncio.create_task(relay.run())

        # ... on shutdown:
        relay.stop()
        await task

    :param publisher: delivery adapter satisfying the :class:`.Publisher` protocol.
    :param batch_size: maximum rows claimed per cycle (default 100).
    :param poll_interval: seconds to wait between cycles when the batch was not full
        (default 1.0).
    :param max_attempts: delivery attempts before a row is marked ``dead`` (default 5).
    :param error_backoff: seconds to sleep after a transient broker error (default 5.0).

    .. seealso:: :class:`.Publisher` - the delivery protocol. :func:`.publish` - manual event
        emission outside of a model signal.
    """

    def __init__(
        self,
        publisher: Publisher,
        *,
        batch_size: int = 100,
        poll_interval: float = 1.0,
        max_attempts: int = 5,
        error_backoff: float = 5.0,
    ) -> None:
        self.publisher = publisher
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self.max_attempts = max_attempts
        self.error_backoff = error_backoff
        self._stopping = asyncio.Event()

    def _claim_stmt(self) -> Any:
        cols = OutboxEvent.__table__.c  # ty: ignore[unresolved-attribute]
        return (
            select(OutboxEvent)
            .where(cols.status.in_((PENDING, FAILED)))
            .order_by(cols.id)
            .with_for_update(skip_locked=True)
            .limit(self.batch_size)
        )

    async def _drain_once(self, sessionmaker: async_sessionmaker[AsyncSession]) -> int:
        cols = OutboxEvent.__table__.c  # ty: ignore[unresolved-attribute]
        async with sessionmaker() as session, session.begin():
            rows = (await session.execute(self._claim_stmt())).scalars().all()
            if not rows:
                return 0
            if hasattr(self.publisher, "publish_batch"):
                await self._publish_batch(session, cols, list(rows))
                return len(rows)
            for row in rows:
                try:
                    await self.publisher.publish(to_message(row))
                except TransientPublishError:
                    raise  # abort the whole batch -> rollback; attempts NOT burned
                except Exception as e:  # any other publisher error = per-event poison
                    attempts = row.attempts + 1
                    status = DEAD if attempts >= self.max_attempts else FAILED
                    await session.execute(
                        update(OutboxEvent)
                        .where(cols.id == row.id)
                        .values(status=status, attempts=attempts, last_error=str(e))
                    )
                else:
                    await session.execute(
                        update(OutboxEvent)
                        .where(cols.id == row.id)
                        .values(status=PUBLISHED, published_at=_utcnow())
                    )
            return len(rows)

    async def _publish_batch(self, session: AsyncSession, cols: Any, rows: list[Any]) -> None:
        try:
            # publish_batch is an optional capability (not on the Publisher Protocol); the
            # caller gated this on hasattr(self.publisher, "publish_batch").
            await self.publisher.publish_batch([to_message(r) for r in rows])  # ty: ignore[unresolved-attribute]
        except TransientPublishError:
            raise  # whole-batch rollback; attempts NOT burned
        except Exception as e:  # whole-batch poison (insert is all-or-nothing)
            for row in rows:
                attempts = row.attempts + 1
                status = DEAD if attempts >= self.max_attempts else FAILED
                await session.execute(
                    update(OutboxEvent)
                    .where(cols.id == row.id)
                    .values(status=status, attempts=attempts, last_error=str(e))
                )
        else:
            now = _utcnow()
            await session.execute(
                update(OutboxEvent)
                .where(cols.id.in_([r.id for r in rows]))
                .values(status=PUBLISHED, published_at=now)
            )

    def stop(self) -> None:
        """Signal the relay loop to stop after the current cycle completes."""
        self._stopping.set()

    async def _wait(self, timeout: float) -> None:
        try:
            await asyncio.wait_for(self._stopping.wait(), timeout)
        except TimeoutError:
            pass

    async def run(self) -> None:
        """Start the relay polling loop; blocks until :meth:`stop` is called or cancelled.

        Spawns no threads.  Designed to run as an ``asyncio`` task.  Cancellation is handled
        gracefully: the stopping event is set and ``CancelledError`` is re-raised.

        .. note::

            Requires alchemiq to be configured (``configure`` called) before ``run()`` is
            awaited.
        """
        sessionmaker = require_sessionmaker()
        try:
            while not self._stopping.is_set():
                try:
                    drained = await self._drain_once(sessionmaker)
                except TransientPublishError:
                    await self._wait(self.error_backoff)
                    continue
                if drained < self.batch_size:
                    await self._wait(self.poll_interval)
        except asyncio.CancelledError:
            self._stopping.set()
            raise
