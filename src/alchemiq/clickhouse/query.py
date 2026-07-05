"""ClickHouseQuerySet: immutable query builder and SQL renderer for ClickHouse models."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from clickhouse_sqlalchemy.drivers.base import ClickHouseDialect  # ty: ignore[unresolved-import]
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.orm.instrumentation import manager_of_class

from alchemiq.exceptions import ClickHouseError, ConfigError
from alchemiq.query.q import Q
from alchemiq.query.soft_delete import EXCLUDE, INCLUDE, ONLY, is_soft_delete

_DIALECT = ClickHouseDialect()


class ClickHouseQuerySet:
    """Immutable query builder for a ClickHouse model.

    Compiles to a SQLAlchemy ``Select`` via the shared query compiler, then renders
    to a ClickHouse SQL string (with ``FINAL`` injected where needed).  Every
    method returns a **new** instance - the original is unchanged.

    Typically obtained via :class:`.ClickHouseRepository` methods rather than
    constructed directly.

    .. seealso:: :class:`.ClickHouseRepository` - factory for querysets.
    """

    def __init__(
        self,
        model: type,
        *,
        where: tuple[Q, ...] = (),
        order: tuple[str, ...] = (),
        limit: int | None = None,
        offset: int | None = None,
        distinct: bool = False,
        projection: tuple[str, ...] | None = None,
        deleted: str = EXCLUDE,
        final: bool | None = None,
    ) -> None:
        self.model = model
        self._where = where
        self._order = order
        self._limit = limit
        self._offset = offset
        self._distinct = distinct
        self._projection = projection
        self._deleted = deleted
        # None = use the model default (True for soft-delete models, False otherwise).
        # An explicit bool overrides the default - used by with_deleted()/only_deleted()
        # to disable FINAL (CH 24.x FINAL removes is_deleted=1 tombstone rows).
        self._final = is_soft_delete(model) if final is None else final
        # CH has no relation loading:
        self._select_related: tuple[str, ...] = ()
        self._prefetch_related: tuple[str, ...] = ()

    def _clone(self, **changes: Any) -> ClickHouseQuerySet:
        kw: dict[str, Any] = {
            "where": self._where,
            "order": self._order,
            "limit": self._limit,
            "offset": self._offset,
            "distinct": self._distinct,
            "projection": self._projection,
            "deleted": self._deleted,
            "final": self._final,
        }
        kw.update(changes)
        return ClickHouseQuerySet(self.model, **kw)

    def filter(self, *args: Q, **lookups: Any) -> ClickHouseQuerySet:
        """Return a new queryset with an additional WHERE condition."""
        return self._clone(where=self._where + (Q(*args, **lookups),))

    def exclude(self, *args: Q, **lookups: Any) -> ClickHouseQuerySet:
        """Return a new queryset with an additional negated WHERE condition."""
        return self._clone(where=self._where + (~Q(*args, **lookups),))

    def order_by(self, *fields: str) -> ClickHouseQuerySet:
        """Return a new queryset with the given ORDER BY columns (prefix '-' to reverse)."""
        return self._clone(order=tuple(fields))

    def limit(self, n: int) -> ClickHouseQuerySet:
        """Return a new queryset with a LIMIT clause."""
        return self._clone(limit=n)

    def offset(self, n: int) -> ClickHouseQuerySet:
        """Return a new queryset with an OFFSET clause."""
        return self._clone(offset=n)

    def distinct(self) -> ClickHouseQuerySet:
        """Return a new queryset with SELECT DISTINCT."""
        return self._clone(distinct=True)

    def only(self, *fields: str) -> ClickHouseQuerySet:
        """Return a new queryset that SELECTs only *fields* (column projection)."""
        return self._clone(projection=tuple(fields))

    def final(self) -> ClickHouseQuerySet:
        """Return a new queryset that appends FINAL to the FROM clause.

        FINAL instructs ClickHouse to collapse duplicate ORDER BY keys at query time
        (ReplacingMergeTree). For soft-delete models this is the default; call this
        explicitly for non-soft-delete MergeTree models that need deduplication.
        """
        return self._clone(final=True)

    def with_deleted(self) -> ClickHouseQuerySet:
        """Include soft-deleted rows in results (soft-delete models only).

        Disables ``FINAL`` and removes the ``is_deleted`` filter so the raw row history
        is returned - live rows and tombstone rows are both visible as physical rows.

        :raises ConfigError: if ``Meta.soft_delete`` is not ``True`` on the model.

        .. seealso:: ``only_deleted`` - return only the tombstone rows.
        """
        if not is_soft_delete(self.model):
            raise ConfigError(
                f"{self.model.__name__} is not soft-delete; with_deleted() unavailable"
            )
        # CH FINAL removes is_deleted=1 tombstones from results, so to see live+deleted we
        # disable FINAL and apply NO deleted_at filter (INCLUDE). Without FINAL the result is
        # the raw, un-collapsed row history (a deleted key shows both its live and tombstone rows).
        return self._clone(deleted=INCLUDE, final=False)

    def only_deleted(self) -> ClickHouseQuerySet:
        """Return only soft-deleted rows (``deleted_at IS NOT NULL``), without ``FINAL``.

        Filters on the application-level ``deleted_at`` timestamp (``IS NOT NULL``),
        not the engine-level ``is_deleted=1`` tombstone marker (which only drives
        ``FINAL`` collapse).

        :raises ConfigError: if ``Meta.soft_delete`` is not ``True`` on the model.

        .. seealso:: ``with_deleted`` - include both live and deleted rows.
        """
        if not is_soft_delete(self.model):
            raise ConfigError(
                f"{self.model.__name__} is not soft-delete; only_deleted() unavailable"
            )
        # Same reasoning as with_deleted(): no FINAL, filter deleted_at IS NOT NULL.
        return self._clone(deleted=ONLY, final=False)

    async def all(self) -> list[Any]:
        """Execute the query and return all matching model instances."""
        from alchemiq.clickhouse.connection import get_clickhouse_client

        client = await get_clickhouse_client()
        result = await client.query(render_sql(self))
        return _rows_to_instances(self.model, list(result.column_names), list(result.result_rows))

    async def first(self) -> Any | None:
        """Return the first matching instance, or None if no rows match."""
        rows = await self._clone(limit=1).all()
        return rows[0] if rows else None

    async def count(self) -> int:
        """Return the number of rows matching the current filters."""
        from alchemiq.clickhouse.connection import get_clickhouse_client

        inner = render_sql(self._clone(order=(), limit=None, offset=None))
        client = await get_clickhouse_client()
        result = await client.query(f"SELECT count() FROM ({inner})")
        return int(result.result_rows[0][0])

    async def exists(self) -> bool:
        """Return True if at least one row matches the current filters."""
        rows = await self._clone(limit=1).all()
        return bool(rows)

    async def get_or_none(self, *args: Q, **lookups: Any) -> Any | None:
        """Return exactly one matching instance, ``None`` if none match.

        :param args: :class:`.Q` expressions to filter on.
        :param lookups: Keyword filter arguments (``column=value``).
        :return: The matching instance, or ``None`` if no rows match.
        :raises MultipleResultsFound: if more than one row matches.
        """
        qs = self.filter(*args, **lookups) if (args or lookups) else self
        rows = await qs._clone(limit=2).all()
        if not rows:
            return None
        if len(rows) > 1:
            from alchemiq.exceptions import MultipleResultsFound

            raise MultipleResultsFound(
                f"get_or_none() returned more than one {self.model.__name__}"
            )
        return rows[0]

    async def iterate(self, batch_size: int) -> AsyncIterator[list[Any]]:
        """Stream results in batches of *batch_size* rows via clickhouse-connect block streaming."""
        from alchemiq.clickhouse.connection import get_clickhouse_client

        client = await get_clickhouse_client()
        sql = render_sql(self)
        stream = await client.query_row_block_stream(sql, settings={"max_block_size": batch_size})
        async with stream:
            async for block in stream:
                yield _rows_to_instances(self.model, list(stream.source.column_names), list(block))

    def compile(self) -> Any:
        """Return the compiled SQLAlchemy Select statement (without FINAL injection)."""
        from alchemiq.query.compiler import compile_select

        # FINAL injection is handled in render_sql() via SQL string post-processing;
        # with_hint() produces Oracle-style comments, not CH's FROM <table> FINAL.
        return compile_select(self)


def _db_name_to_key(model: type) -> dict[str, str]:
    return {c.name: c.key for c in model.__table__.columns}  # ty: ignore[unresolved-attribute]


def _rows_to_instances(model: type, column_names: list[str], rows: list[tuple]) -> list[Any]:
    name_to_key = _db_name_to_key(model)
    mgr = manager_of_class(model)
    out = []
    for row in rows:
        inst = mgr.new_instance()  # creates instance with _sa_instance_state, bypasses __init__
        for col_name, value in zip(column_names, row, strict=False):
            key = name_to_key.get(col_name)
            if key is not None:
                set_committed_value(inst, key, value)
        out.append(inst)
    return out


def render_sql(qs: ClickHouseQuerySet) -> str:
    """Compile *qs* to a ClickHouse SQL string, injecting FINAL into the FROM clause if needed."""
    import re

    stmt = qs.compile()
    # literal_binds inlines values into the SQL string (CH client takes a SQL string here);
    # server-side parameter binding is not yet implemented.
    compiled = stmt.compile(dialect=_DIALECT, compile_kwargs={"literal_binds": True})
    sql = str(compiled)
    if qs._final:
        # The CH SQL compiler's FINAL mechanism (_final_clause on Select) is not
        # propagated through the SA ORM plugin rewrite that occurs during compilation.
        # We inject FINAL after the FROM <tablename> clause via string post-processing.
        # This is reliable: CH queries have no JOINs, and the tablename is stable.
        # The regex is whitespace-tolerant (no hard \n requirement) so it works regardless
        # of how SQLAlchemy renders the FROM clause.
        tablename = re.escape(qs.model.__tablename__)  # ty: ignore[unresolved-attribute]
        sql, n = re.subn(rf"(\bFROM {tablename})\b", r"\1 FINAL", sql, count=1)
        if n != 1:
            raise ClickHouseError(
                f"FINAL injection failed for {qs.model.__tablename__}:"  # ty: ignore[unresolved-attribute]
                f" expected exactly 1 FROM-clause substitution, got {n}"
            )
    return sql
