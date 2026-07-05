"""ClickHouseRepository and BufferedInserter - data-access layer for ClickHouse models."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable
from typing import Any, Generic, TypeVar, get_args, get_origin

from alchemiq.clickhouse.query import ClickHouseQuerySet
from alchemiq.exceptions import ClickHouseError, UnsupportedOperationError
from alchemiq.query.q import Q

logger = logging.getLogger("alchemiq.clickhouse")

M = TypeVar("M")


def _col_value(obj: Any, col: Any) -> Any:
    """Return the effective column value, applying SA column defaults for None slots.

    Canonical insert value-extraction for all CH inserts: applies SA scalar/callable
    column defaults that the ORM would normally invoke, covering soft-delete columns
    (is_deleted=0, _version=now(), deleted_at=None) and any user-defined defaults.

    SA callable/scalar column defaults are only invoked during ORM inserts; since
    _insert_rows bypasses the ORM, we apply them manually here so soft-delete
    columns (is_deleted UInt8 default 0, _version DateTime64 default now(), ...)
    receive their correct values when not explicitly provided.

    For non-nullable columns without a SA default where the Python value is None
    (e.g. non-key columns in tombstone rows), we supply the ClickHouse zero value
    for the column type ("" for String, epoch for DateTime64, 0 for numeric) so
    the clickhouse-connect driver doesn't reject the row.
    """
    import datetime as dt

    from clickhouse_sqlalchemy import types as ch  # ty: ignore[unresolved-import]
    from sqlalchemy import String as SAString

    val = getattr(obj, col.key)
    if val is None and col.default is not None:
        d = col.default
        if d.is_callable:
            try:
                return d.arg(None)  # SA convention: pass ExecutionContext (we pass None)
            except TypeError:
                return d.arg()  # 0-arg lambda
        elif not d.is_sequence and d.arg is not None:
            return d.arg  # scalar default (skip None-valued scalars like deleted_at=None)
    if val is None and not col.nullable:
        # Non-nullable column with no SA default and no Python value supplied
        # (common for non-key columns in tombstone rows). Supply the CH zero value.
        ct = col.type
        if isinstance(ct, ch.Nullable):
            return None  # wrapped type is nullable; None is valid
        if isinstance(ct, (ch.String, SAString)):
            return ""
        if isinstance(ct, ch.DateTime64):
            return dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
        return 0  # numeric types: UInt8/16/32/64, Int8/16/32/64, Float32/64
    return val


async def _insert_rows(model: type, objs: list[Any]) -> None:
    from alchemiq.clickhouse.connection import get_clickhouse_client

    if not objs:
        return
    cols = list(model.__table__.columns)  # ty: ignore[unresolved-attribute]
    db_names = [c.name for c in cols]
    data = [[_col_value(o, col) for col in cols] for o in objs]
    client = await get_clickhouse_client()
    await client.insert(model.__tablename__, data, column_names=db_names)  # ty: ignore[unresolved-attribute]


class ClickHouseRepository(Generic[M]):  # noqa: UP046
    """Data-access surface for one ClickHouse model.

    No transactions, UnitOfWork, signals, or cache - ClickHouse is append-only.
    Instantiate directly with a model class, or subclass with a type parameter:

    E.g.::

        from alchemiq.clickhouse import ClickHouseRepository

        # direct:
        repo = ClickHouseRepository(PageView)
        await repo.insert(PageView(event_time=now, user_id=42))

        # typed subclass:
        class PageViewRepo(ClickHouseRepository[PageView]):
            pass

        repo = PageViewRepo()
        rows = await repo.filter(user_id=42).order_by("event_time").all()

    .. seealso:: :class:`.ClickHouseModel` - declare the table schema.
    .. seealso:: ``ClickHouseQuerySet`` - chainable query builder returned by
        ``filter``, ``order_by``, and related methods.
    """

    model: type[M]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for base in getattr(cls, "__orig_bases__", ()):
            if get_origin(base) is ClickHouseRepository:
                args = get_args(base)
                if args and isinstance(args[0], type):
                    cls.model = args[0]
                    break

    def __init__(self, model: type[M] | None = None) -> None:
        resolved = model if model is not None else getattr(type(self), "model", None)
        if resolved is None:
            raise TypeError(
                "ClickHouseRepository needs a model: ClickHouseRepository(Model) or subclass"
            )
        self.model = resolved

    def _qs(self) -> ClickHouseQuerySet:
        return ClickHouseQuerySet(self.model)

    def filter(self, *args: Q, **lookups: Any) -> ClickHouseQuerySet:
        """Return a queryset for this model with an additional WHERE condition."""
        return self._qs().filter(*args, **lookups)

    def exclude(self, *args: Q, **lookups: Any) -> ClickHouseQuerySet:
        """Return a queryset for this model with an additional negated WHERE condition."""
        return self._qs().exclude(*args, **lookups)

    def order_by(self, *fields: str) -> ClickHouseQuerySet:
        """Return a queryset ordered by *fields* (prefix '-' to reverse)."""
        return self._qs().order_by(*fields)

    def limit(self, n: int) -> ClickHouseQuerySet:
        """Return a queryset with a LIMIT clause."""
        return self._qs().limit(n)

    def offset(self, n: int) -> ClickHouseQuerySet:
        """Return a queryset with an OFFSET clause."""
        return self._qs().offset(n)

    def distinct(self) -> ClickHouseQuerySet:
        """Return a queryset with SELECT DISTINCT."""
        return self._qs().distinct()

    def only(self, *fields: str) -> ClickHouseQuerySet:
        """Return a queryset that selects only *fields* (column projection)."""
        return self._qs().only(*fields)

    def final(self) -> ClickHouseQuerySet:
        """Return a queryset with FINAL appended to the FROM clause."""
        return self._qs().final()

    def with_deleted(self) -> ClickHouseQuerySet:
        """Return a queryset that includes soft-deleted rows (raw history, no FINAL)."""
        return self._qs().with_deleted()

    def only_deleted(self) -> ClickHouseQuerySet:
        """Return a queryset that returns only soft-deleted rows (no FINAL)."""
        return self._qs().only_deleted()

    async def all(self) -> list[M]:
        """Fetch all rows and return them as model instances."""
        return await self._qs().all()

    async def first(self) -> M | None:
        """Return the first row as a model instance, or None if the table is empty."""
        return await self._qs().first()

    async def count(self, *args: Q, **lookups: Any) -> int:
        """Return the number of rows matching the optional filters."""
        qs = self._qs().filter(*args, **lookups) if (args or lookups) else self._qs()
        return await qs.count()

    async def exists(self, *args: Q, **lookups: Any) -> bool:
        """Return True if at least one row matches the optional filters."""
        qs = self._qs().filter(*args, **lookups) if (args or lookups) else self._qs()
        return await qs.exists()

    async def get_or_none(self, *args: Q, **lookups: Any) -> M | None:
        """Return exactly one matching instance, ``None`` if none match.

        :param args: :class:`.Q` expressions to filter on.
        :param lookups: Keyword filter arguments (``column=value``).
        :return: The matching instance, or ``None`` if no rows match.
        :raises MultipleResultsFound: if more than one row matches.
        """
        return await self._qs().get_or_none(*args, **lookups)

    def iterate(self, batch_size: int) -> AsyncIterator[list[M]]:
        """Stream all rows in batches of *batch_size* via clickhouse-connect block streaming."""
        return self._qs().iterate(batch_size)

    async def raw(
        self, sql: str, params: dict[str, Any] | None = None, *, as_model: bool = False
    ) -> list[Any]:
        """Execute a raw SQL string and return results.

        E.g.::

            repo = ClickHouseRepository(Sale)
            rows = await repo.raw(
                "SELECT region, sum(amount) AS total FROM _sale GROUP BY region ORDER BY region"
            )
            # rows == [{"region": "EU", "total": 30}, ...]

        :param sql: A literal ClickHouse SQL query string.
        :param params: Optional query parameters passed to ``clickhouse-connect``.
        :param as_model: If ``True``, hydrate rows into model instances; otherwise
            return plain dicts keyed by column name.
        :return: List of dicts (default) or model instances when ``as_model=True``.
        """
        from alchemiq.clickhouse.connection import get_clickhouse_client
        from alchemiq.clickhouse.query import _rows_to_instances

        client = await get_clickhouse_client()
        result = await client.query(sql, parameters=params)
        cols = list(result.column_names)
        rows = list(result.result_rows)
        if as_model:
            return _rows_to_instances(self.model, cols, rows)
        return [dict(zip(cols, r, strict=False)) for r in rows]

    def buffered(
        self,
        *,
        max_rows: int = 10_000,
        flush_interval: float = 5.0,
        max_buffered: int | None = None,
    ) -> BufferedInserter:
        """Return a :class:`.BufferedInserter` backed by this repository.

        The inserter accumulates rows in memory and flushes them to ClickHouse when
        ``max_rows`` is reached or every ``flush_interval`` seconds.  Use as an async
        context manager to guarantee the final flush on exit.

        E.g.::

            async with repo.buffered(max_rows=1000, flush_interval=5.0) as buf:
                for event in events:
                    await buf.add(event)
            # all rows flushed when the block exits

        :param max_rows: Flush automatically once this many rows accumulate (default 10 000).
        :param flush_interval: Maximum seconds between automatic timer-driven flushes (default 5).
        :param max_buffered: Hard cap on in-memory rows; :meth:`.BufferedInserter.add` raises
            ``ClickHouseError`` when exceeded.  ``None`` (default) means unbounded.
        :return: A new :class:`.BufferedInserter` instance.
        """
        return BufferedInserter(
            self, max_rows=max_rows, flush_interval=flush_interval, max_buffered=max_buffered
        )

    async def insert(self, obj: M) -> M:
        """Insert a single model instance into ClickHouse and return it.

        E.g.::

            repo = ClickHouseRepository(PageView)
            view = await repo.insert(PageView(event_time=now, user_id=42))

        :param obj: The model instance to insert.
        :return: The same instance (unchanged).
        """
        await _insert_rows(self.model, [obj])
        return obj

    async def bulk_insert(self, objs: Iterable[M]) -> list[M]:
        """Insert multiple model instances in a single ClickHouse call and return them.

        E.g.::

            repo = ClickHouseRepository(PageView)
            await repo.bulk_insert([
                PageView(event_time=t1, user_id=1),
                PageView(event_time=t2, user_id=2),
            ])

        :param objs: Iterable of model instances to insert.
        :return: The inserted instances as a list.
        """
        items = list(objs)
        await _insert_rows(self.model, items)
        return items

    async def update(self, *args: Any, **kw: Any) -> Any:
        """Raise UnsupportedOperationError - ClickHouse does not support row UPDATE."""
        raise UnsupportedOperationError(
            f"{self.model.__name__}: ClickHouse does not support row UPDATE"
        )

    async def bulk_update(self, *args: Any, **kw: Any) -> Any:
        """Raise UnsupportedOperationError - ClickHouse does not support bulk row UPDATE."""
        raise UnsupportedOperationError(
            f"{self.model.__name__}: ClickHouse does not support bulk row UPDATE"
        )

    async def get_or_create(self, *args: Any, **kw: Any) -> Any:
        """Raise UnsupportedOperationError - ClickHouse has no upsert; use insert()."""
        raise UnsupportedOperationError(
            f"{self.model.__name__}: ClickHouse has no upsert; use insert()"
        )

    async def update_or_create(self, *args: Any, **kw: Any) -> Any:
        """Raise UnsupportedOperationError - ClickHouse has no upsert; use bulk_insert()."""
        raise UnsupportedOperationError(
            f"{self.model.__name__}: ClickHouse has no upsert; use bulk_insert()"
        )

    async def delete(self, **lookups: Any) -> None:
        """Soft-delete a row by inserting a tombstone with ``is_deleted=1``.

        Does NOT issue a SQL DELETE.  Instead it appends a new row with the same ORDER
        BY key and ``is_deleted=1``; a subsequent ``SELECT ... FINAL`` collapses the
        key to the latest version and hides the row because ``is_deleted=1``.

        *lookups* must supply every column in the table's ORDER BY key so the
        tombstone lands on the same key as the live row.  Missing key columns are
        caught eagerly before any IO.

        E.g.::

            repo = ClickHouseRepository(Document)
            await repo.insert(Document(key=1, body="hello"))
            await repo.delete(key=1)   # tombstone inserted; row hidden under FINAL

        :param lookups: Keyword arguments identifying the row - must cover every ORDER
            BY column (e.g. ``key=1`` for a single-column key).
        :raises UnsupportedOperationError: if ``Meta.soft_delete`` is not ``True`` or
            if any ORDER BY key column is missing from *lookups*.

        .. seealso:: :meth:`.ClickHouseRepository.restore` - un-delete the row.
        .. seealso:: :meth:`.ClickHouseRepository.cleanup` - physically remove tombstones.
        """
        from alchemiq.query.soft_delete import is_soft_delete

        if not is_soft_delete(self.model):
            raise UnsupportedOperationError(
                f"{self.model.__name__}: row DELETE requires"
                " Meta.soft_delete=True (ReplacingMergeTree)"
            )
        self._validate_order_by_key(lookups, "delete")
        await self.insert(self._tombstone(lookups, deleted=True))

    async def restore(self, **lookups: Any) -> None:
        """Un-delete a row by inserting a live marker with ``is_deleted=0``.

        The inverse of :meth:`.delete`: inserts a new row with the same ORDER BY key,
        ``is_deleted=0``, and a fresh ``_version`` timestamp so
        ``ReplacingMergeTree FINAL`` collapses to this latest (live) version.

        :param lookups: Keyword arguments identifying the row - must cover every ORDER
            BY column (same constraint as :meth:`.delete`).
        :raises UnsupportedOperationError: if ``Meta.soft_delete`` is not ``True`` or
            if any ORDER BY key column is missing from *lookups*.

        .. seealso:: :meth:`.ClickHouseRepository.delete` - soft-delete the row.
        """
        from alchemiq.query.soft_delete import is_soft_delete

        if not is_soft_delete(self.model):
            raise UnsupportedOperationError(
                f"{self.model.__name__} is not soft-delete; restore() unavailable"
            )
        self._validate_order_by_key(lookups, "restore")
        await self.insert(self._tombstone(lookups, deleted=False))

    async def cleanup(self) -> None:
        """Run ``OPTIMIZE TABLE FINAL CLEANUP`` to physically remove tombstone rows.

        After :meth:`.delete`, ClickHouse retains both the live row and the tombstone
        as physical rows on disk.  ``CLEANUP`` instructs the merge engine to drop all
        physical rows for keys where ``is_deleted=1`` once merged.

        Requires ``Meta.soft_delete=True`` and
        ``allow_experimental_replacing_merge_with_cleanup`` enabled on the CH server
        (set in ``Meta.engine`` settings or the server config).

        :raises UnsupportedOperationError: if ``Meta.soft_delete`` is not ``True``.

        .. warning::

            ``CLEANUP`` is an experimental ClickHouse feature.  Enable
            ``allow_experimental_replacing_merge_with_cleanup = 1`` in the engine
            settings or the server configuration before calling this method.

        .. seealso:: :meth:`.ClickHouseRepository.delete` - insert the tombstone first.
        """
        from alchemiq.clickhouse.ddl import optimize
        from alchemiq.query.soft_delete import is_soft_delete

        if not is_soft_delete(self.model):
            raise UnsupportedOperationError(
                f"{self.model.__name__} is not soft-delete; cleanup() unavailable"
            )
        await optimize(self.model, cleanup=True)

    def _validate_order_by_key(self, lookups: dict[str, Any], method: str) -> None:
        """Raise UnsupportedOperationError if lookups omits any ORDER BY column.

        A tombstone row must share the SAME sorting key as the live row so that
        ReplacingMergeTree FINAL can collapse them.  Omitting any ORDER BY column
        causes the tombstone to land on a different key -> the live row stays visible
        and a spurious row is inserted.  We catch this eagerly before any IO.
        """
        from alchemiq.clickhouse.model import ch_engine_of

        engine = ch_engine_of(self.model)
        order_by = engine.order_by
        order_cols: tuple[str, ...] = (order_by,) if isinstance(order_by, str) else tuple(order_by)
        fields: dict[str, Any] = self.model.__alchemiq_fields__  # ty: ignore[unresolved-attribute]
        # Keep only plain column entries (skip SQL expressions like "toYYYYMM(ts)").
        required = tuple(col for col in order_cols if col in fields)
        missing = tuple(col for col in required if col not in lookups)
        if missing:
            raise UnsupportedOperationError(
                f"{self.model.__name__}.{method}() requires all ORDER BY key columns"
                f" {required!r}; missing {missing!r}."
                " ClickHouse soft-delete inserts a tombstone keyed on the full ORDER BY key."
            )

    def _tombstone(self, lookups: dict[str, Any], *, deleted: bool) -> Any:
        """Build a model instance representing a soft-delete or restore marker row."""
        import datetime as dt

        now = dt.datetime.now(dt.UTC)
        values = dict(lookups)
        values["is_deleted"] = 1 if deleted else 0
        values["deleted_at"] = now if deleted else None
        values["_version"] = now
        return self.model(**values)


class BufferedInserter:
    """Accumulates rows in memory; flushes on ``max_rows`` or every ``flush_interval`` seconds.

    Obtain via :meth:`.ClickHouseRepository.buffered` rather than constructing directly.
    Use as an async context manager to ensure all buffered rows are flushed on exit.

    On flush failure the batch is retained and retried on the next flush call.

    .. seealso:: :meth:`.ClickHouseRepository.buffered` - factory method.
    """

    def __init__(
        self,
        repo: ClickHouseRepository,  # type: ignore[type-arg]
        *,
        max_rows: int = 10_000,
        flush_interval: float = 5.0,
        max_buffered: int | None = None,
    ) -> None:
        self._repo = repo
        self._max_rows = max_rows
        self._flush_interval = flush_interval
        self._max_buffered = max_buffered
        self._buffer: list[Any] = []
        self._lock = asyncio.Lock()
        self._stopping = asyncio.Event()
        self._timer: asyncio.Task[None] | None = None

    async def add(self, obj: Any) -> None:
        """Buffer *obj* and flush immediately if ``max_rows`` is reached.

        :param obj: Model instance to buffer.
        :raises ClickHouseError: if ``max_buffered`` is set and the buffer is already full.
        """
        async with self._lock:
            if self._max_buffered is not None and len(self._buffer) >= self._max_buffered:
                raise ClickHouseError(
                    f"BufferedInserter buffer full (max_buffered={self._max_buffered})"
                )
            self._buffer.append(obj)
            ready = self._buffer if len(self._buffer) >= self._max_rows else None
            if ready is not None:
                self._buffer = []
        if ready is not None:
            await self._flush_batch(ready)
        self._ensure_timer()

    async def add_many(self, objs: Any) -> None:
        """Buffer each item in *objs*, flushing on max_rows after each addition."""
        for obj in objs:
            await self.add(obj)

    async def flush(self) -> None:
        """Drain the in-memory buffer and bulk-insert any pending rows immediately."""
        async with self._lock:
            batch = self._buffer
            self._buffer = []
        if batch:
            await self._flush_batch(batch)

    async def _flush_batch(self, batch: list[Any]) -> None:
        try:
            await self._repo.bulk_insert(batch)
        except Exception:  # retain on failure; retried next tick / flush / close
            logger.exception("ClickHouse buffered flush failed; retaining %s rows", len(batch))
            async with self._lock:
                self._buffer = batch + self._buffer

    def _ensure_timer(self) -> None:
        if self._timer is None:
            self._timer = asyncio.create_task(self._run_timer())

    async def _run_timer(self) -> None:
        while not self._stopping.is_set():
            try:
                await asyncio.wait_for(self._stopping.wait(), self._flush_interval)
            except TimeoutError:
                await self.flush()
            except asyncio.CancelledError:
                self._stopping.set()
                break

    async def close(self) -> None:
        """Stop the background timer and flush any remaining buffered rows."""
        self._stopping.set()
        if self._timer is not None:
            try:
                await self._timer
            except asyncio.CancelledError:
                pass  # timer was cancelled externally; still flush below
            self._timer = None
        await self.flush()

    async def __aenter__(self) -> BufferedInserter:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
