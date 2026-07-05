"""QuerySet: immutable lazy query builder and async terminal operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, cast

from alchemiq.exceptions import ConfigError, MultipleResultsFound, NotFoundError
from alchemiq.query.q import Q
from alchemiq.query.soft_delete import (
    EXCLUDE,
    INCLUDE,
    ONLY,
    DeletedMode,
    deleted_predicate,
    is_soft_delete,
)

if TYPE_CHECKING:
    from alchemiq.query.aggregates import Aggregate
    from alchemiq.repository.pagination import CursorPage, Page


def pk_name(model: type) -> str:
    """Return the name of the primary-key field declared on *model*.

    Scans ``model.__alchemiq_fields__`` for the field whose
    ``field.config.primary_key`` is True and returns its name.
    Raises ``ConfigError`` if no primary key is found.
    """
    fields: dict[str, Any] = getattr(model, "__alchemiq_fields__", {})
    for name, field in fields.items():
        if field.config.primary_key:
            return name
    raise ConfigError(f"{model.__name__} has no primary key")


class QuerySet:
    """Immutable, lazy query builder. Compiles to a SQLAlchemy Select (no I/O)."""

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
        select_related: tuple[str, ...] = (),
        prefetch_related: tuple[str, ...] = (),
        deleted: DeletedMode = EXCLUDE,
        cache: Any = None,
        cache_ttl: int | None = None,
    ) -> None:
        self.model = model
        self._where = where
        self._order = order
        self._limit = limit
        self._offset = offset
        self._distinct = distinct
        self._projection = projection
        self._select_related = select_related
        self._prefetch_related = prefetch_related
        self._deleted = deleted
        self._cache = cache
        self._cache_ttl = cache_ttl

    def _clone(self, **changes: Any) -> QuerySet:
        kw: dict[str, Any] = {
            "where": self._where,
            "order": self._order,
            "limit": self._limit,
            "offset": self._offset,
            "distinct": self._distinct,
            "projection": self._projection,
            "select_related": self._select_related,
            "prefetch_related": self._prefetch_related,
            "deleted": self._deleted,
            "cache": self._cache,
            "cache_ttl": self._cache_ttl,
        }
        kw.update(changes)
        return QuerySet(self.model, **kw)

    def _should_cache_rows(self) -> bool:
        return (
            self._cache is not None
            and not self._select_related
            and not self._prefetch_related
            and self._projection is None
        )

    def select_related(self, *names: str) -> QuerySet:
        """Join-load the named relationships via a SQL JOIN in the same query.

        Uses SQLAlchemy ``joinedload``; the related object is available on the
        result without triggering a lazy load.  For collections, prefer
        :meth:`.QuerySet.prefetch_related` (a separate SELECT avoids row
        duplication from the JOIN).

        E.g.::

            track = await QuerySet(Track).select_related("artist").filter(id=1).first()
            print(track.artist.name)  # no RelationNotLoaded

        :param names: relationship attribute names to join-load.

        .. seealso:: :meth:`.QuerySet.prefetch_related` - uses selectinload (separate SELECT).
        """
        return self._clone(select_related=self._select_related + names)

    def prefetch_related(self, *names: str) -> QuerySet:
        """Eager-load the named relationships via a separate SELECT ... IN (...) query.

        Uses SQLAlchemy ``selectinload``; the related collection is populated
        without a JOIN (no row duplication).  For to-one relationships where you
        need the foreign object in the same query, prefer :meth:`.QuerySet.select_related`.

        E.g.::

            artist = await QuerySet(Artist).prefetch_related("tracks").filter(id=1).first()
            print([t.title for t in artist.tracks])  # no RelationNotLoaded

        :param names: relationship attribute names to selectin-load.

        .. seealso:: :meth:`.QuerySet.select_related` - uses joinedload (same-query JOIN).
        """
        return self._clone(prefetch_related=self._prefetch_related + names)

    def with_deleted(self) -> QuerySet:
        """Include soft-deleted (tombstoned) rows in results.

        By default, soft-delete models exclude tombstone rows (``deleted_at IS NULL``).
        Call this builder to include them as well.

        E.g.::

            all_docs = await QuerySet(Document).with_deleted().all()

        :raises ConfigError: if the model does not have ``Meta.soft_delete = True``.

        .. seealso:: :meth:`.QuerySet.only_deleted` - restrict to tombstones only.
        """
        if not is_soft_delete(self.model):
            raise ConfigError(
                f"{self.model.__name__} is not soft-delete (Meta.soft_delete=True); "
                "with_deleted() is unavailable"
            )
        return self._clone(deleted=INCLUDE)

    def only_deleted(self) -> QuerySet:
        """Restrict results to soft-deleted rows only (``deleted_at IS NOT NULL``).

        E.g.::

            tombstones = await QuerySet(Document).only_deleted().all()

        :raises ConfigError: if the model does not have ``Meta.soft_delete = True``.

        .. seealso:: :meth:`.QuerySet.with_deleted` - include both live and deleted rows.
        """
        if not is_soft_delete(self.model):
            raise ConfigError(
                f"{self.model.__name__} is not soft-delete (Meta.soft_delete=True); "
                "only_deleted() is unavailable"
            )
        return self._clone(deleted=ONLY)

    def filter(self, *args: Q, **lookups: Any) -> QuerySet:
        """Narrow results by AND-ing the given ``Q`` objects and keyword lookups."""
        return self._clone(where=self._where + (Q(*args, **lookups),))

    def exclude(self, *args: Q, **lookups: Any) -> QuerySet:
        """Exclude rows matching the given ``Q`` objects or keyword lookups (NOT AND)."""
        return self._clone(where=self._where + (~Q(*args, **lookups),))

    def order_by(self, *fields: str) -> QuerySet:
        """Set the ORDER BY clause. Prefix a field name with ``-`` for descending."""
        return self._clone(order=tuple(fields))

    def limit(self, n: int) -> QuerySet:
        """Apply a LIMIT clause."""
        return self._clone(limit=n)

    def offset(self, n: int) -> QuerySet:
        """Apply an OFFSET clause."""
        return self._clone(offset=n)

    def distinct(self) -> QuerySet:
        """Deduplicate rows with SELECT DISTINCT."""
        return self._clone(distinct=True)

    def only(self, *fields: str) -> QuerySet:
        """Restrict the SELECT to *fields* (column projection)."""
        return self._clone(projection=tuple(fields))

    def __getitem__(self, item: slice) -> QuerySet:
        if not isinstance(item, slice):
            raise TypeError("QuerySet supports slicing only; integer indexing is not supported")
        if item.step is not None:
            raise ValueError("QuerySet slicing does not support a step")
        start = item.start or 0
        if start < 0 or (item.stop is not None and item.stop < 0):
            raise ValueError("QuerySet slicing does not support negative bounds")
        changes: dict[str, Any] = {"offset": start or None}
        if item.stop is not None:
            changes["limit"] = item.stop - start
        return self._clone(**changes)

    def compile(self) -> Any:
        """Return the SQLAlchemy ``Select`` statement without executing it."""
        from alchemiq.query.compiler import compile_select

        return compile_select(self)

    async def all(self) -> list[Any]:
        """Execute the query and return all matching model instances.

        E.g.::

            users = await QuerySet(User).filter(status="active").all()
        """
        if self._should_cache_rows():
            from alchemiq.cache import ops

            return await ops.read_list(self, self._all_uncached)
        return await self._all_uncached()

    async def _all_uncached(self) -> list[Any]:
        """Execute the query and return all matching model instances."""
        from alchemiq.repository.loading import apply_loaders
        from alchemiq.runtime.session import session_scope

        stmt = apply_loaders(
            self.compile(), self.model, self._select_related, self._prefetch_related
        )
        async with session_scope(write=False) as session:
            result = await session.execute(stmt)
            return list(result.scalars().unique().all())

    async def first(self) -> Any | None:
        """Execute with ``LIMIT 1`` and return the first result, or ``None``.

        E.g.::

            user = await QuerySet(User).order_by("created_at").first()
        """
        rows = await self._clone(limit=1).all()
        return rows[0] if rows else None

    async def count(self) -> int:
        """Return the number of rows matching the current filters.

        Strips ``ORDER BY`` / ``LIMIT`` / ``OFFSET`` before wrapping in
        ``SELECT count(*) FROM (...) AS subquery``.

        E.g.::

            total = await QuerySet(User).filter(status="active").count()
        """
        if self._cache is not None:
            from alchemiq.cache import ops

            return await ops.read_count(self, self._count_uncached)
        return await self._count_uncached()

    async def _count_uncached(self) -> int:
        from sqlalchemy import func, select

        from alchemiq.runtime.session import session_scope

        inner = self.compile().order_by(None).limit(None).offset(None).subquery()
        stmt = select(func.count()).select_from(inner)
        async with session_scope(write=False) as session:
            return int((await session.execute(stmt)).scalar_one())

    async def aggregate(self, **exprs: Aggregate) -> dict[str, Any]:
        """Compute reduce-aggregates over the filtered set and return ``{alias: value}``.

        Each keyword argument is a :class:`.Count` / :class:`.Sum` / :class:`.Avg` /
        :class:`.Min` / :class:`.Max` expression.  Inherits the
        current filters, soft-delete predicate, and any traversal joins.
        No ``GROUP BY``; always one row.  ``Sum`` / ``Avg`` / ``Min`` / ``Max``
        over an empty set return ``None``; ``Count`` returns ``0``.

        E.g.::

            result = await QuerySet(Order).filter(status="paid").aggregate(
                total=Sum("amount"),
                n=Count(),
            )
            print(result["total"], result["n"])

        :param exprs: ``alias=Aggregate(...)`` pairs.
        :return: dict mapping each alias to its computed value.
        :raises ValueError: if no expressions are given.
        """
        if not exprs:
            raise ValueError("aggregate() requires at least one expression")
        from alchemiq.runtime.session import session_scope

        labeled = [expr.resolve(self.model).label(alias) for alias, expr in exprs.items()]
        stmt = (
            self.compile()
            .with_only_columns(*labeled, maintain_column_froms=True)
            .order_by(None)
            .limit(None)
            .offset(None)
        )
        async with session_scope(write=False) as session:
            row = (await session.execute(stmt)).one()
        return dict(zip(exprs.keys(), row, strict=True))

    async def explain(
        self, *, analyze: bool = False, format: Literal["text", "json"] = "text"
    ) -> str | list[Any]:
        """Run ``EXPLAIN`` on the compiled ``SELECT`` and return the query plan.

        ``analyze=True`` executes the query for real timings (read-only
        ``SELECT`` inside a rolled-back transaction on PostgreSQL).
        ``format="json"`` returns the parsed JSON plan (a ``list``);
        ``format="text"`` returns the plan as a ``str``.  Always hits the
        database - never cached.  PostgreSQL only.

        E.g.::

            plan = await QuerySet(User).filter(status="active").explain(analyze=True)
            print(plan)

        :param analyze: when ``True``, run ``EXPLAIN ANALYZE`` (real execution).
        :param format: ``"text"`` (default) or ``"json"``.
        :return: plan string (``format="text"``) or parsed list (``format="json"``).
        """
        import json

        from alchemiq.query.explain import _Explain
        from alchemiq.runtime.session import session_scope

        stmt = _Explain(self.compile(), analyze=analyze, fmt=format)
        async with session_scope(write=False) as session:
            result = await session.execute(stmt)
            rows = [row[0] for row in result.all()]
        if format == "json":
            plan = rows[0] if rows else []
            return json.loads(plan) if isinstance(plan, str) else plan
        return "\n".join(str(r) for r in rows)

    async def exists(self) -> bool:
        """Return ``True`` if at least one row matches the current filters.

        E.g.::

            if await QuerySet(User).filter(email="ada@x.io").exists():
                ...
        """
        if self._cache is not None:
            from alchemiq.cache import ops

            return await ops.read_exists(self, self._exists_uncached)
        return await self._exists_uncached()

    async def _exists_uncached(self) -> bool:
        from alchemiq.runtime.session import session_scope

        async with session_scope(write=False) as session:
            result = await session.execute(self.compile().order_by(None).limit(1))
            return result.first() is not None

    async def get(self, *args: Q, **lookups: Any) -> Any:
        """Filter and return the single matching instance.

        Fetches at most 2 rows to detect duplicates without a full scan.
        Accepts the same ``Q`` and keyword arguments as :meth:`.QuerySet.filter`.

        E.g.::

            user = await QuerySet(User).get(id=42)

        :raises NotFoundError: if no rows match the current filters.
        :raises MultipleResultsFound: if more than one row matches.
        """
        qs = self.filter(*args, **lookups) if (args or lookups) else self
        rows = await qs._clone(limit=2).all()
        if not rows:
            raise NotFoundError(f"{self.model.__name__} matching query does not exist")
        if len(rows) > 1:
            raise MultipleResultsFound(f"get() returned more than one {self.model.__name__}")
        return rows[0]

    async def get_or_none(self, *args: Q, **lookups: Any) -> Any | None:
        """Filter and return the single matching instance, or ``None`` if not found.

        :raises MultipleResultsFound: if more than one row matches.
        """
        qs = self.filter(*args, **lookups) if (args or lookups) else self
        rows = await qs._clone(limit=2).all()
        if not rows:
            return None
        if len(rows) > 1:
            raise MultipleResultsFound(
                f"get_or_none() returned more than one {self.model.__name__}"
            )
        return rows[0]

    async def paginate(self, page: int = 1, size: int = 20) -> Page[Any]:
        """Return a :class:`.Page` of results for page/size pagination.

        Issues two queries: ``count()`` then a windowed ``all()``.

        E.g.::

            page = await QuerySet(User).order_by("id").paginate(page=1, size=20)
            print(page.total, page.items)

        :param page: 1-based page number.
        :param size: number of items per page.
        :raises ValueError: if ``page < 1`` or ``size < 1``.

        .. note::

            ``count()`` and ``all()`` run in two separate database sessions.
            A row inserted between the two queries may inflate ``total``
            without appearing in ``items``, or vice versa.

        .. seealso:: :meth:`.QuerySet.cursor_paginate` - keyset pagination with no ``total``.
        """
        from alchemiq.repository.pagination import Page

        if page < 1 or size < 1:
            raise ValueError("paginate() requires page >= 1 and size >= 1")
        total = await self.count()
        items = await self[(page - 1) * size : page * size].all()
        return Page.build(items=items, total=total, page=page, size=size)

    async def cursor_paginate(
        self, *, size: int = 20, after: str | None = None, before: str | None = None
    ) -> CursorPage[Any]:
        """Keyset (cursor) pagination with no total-count query.

        Adds a PK tiebreaker to the effective order for a deterministic total order.
        ``after`` and ``before`` are mutually exclusive opaque tokens from
        :attr:`.CursorPage.next_cursor` / :attr:`.CursorPage.prev_cursor`.

        E.g.::

            p1 = await QuerySet(User).order_by("id").cursor_paginate(size=20)
            if p1.has_next:
                p2 = await QuerySet(User).order_by("id").cursor_paginate(
                    size=20, after=p1.next_cursor
                )

        :param size: maximum number of items per page (must be >= 1).
        :param after: opaque forward cursor token; fetch the page after this position.
        :param before: opaque backward cursor token; fetch the page before this position.
        :raises ValueError: if ``size < 1`` or both ``after`` and ``before`` are given.
        :raises InvalidCursorError: if a cursor token is malformed or does not match the
            current order.

        .. seealso:: :meth:`.QuerySet.paginate` - offset pagination with a ``total`` count.
        """
        if size < 1:
            raise ValueError("cursor_paginate() requires size >= 1")
        if after is not None and before is not None:
            raise ValueError("cursor_paginate() accepts at most one of after/before")
        from alchemiq.query.compiler import _order_columns
        from alchemiq.query.cursor import (
            build_seek,
            decode_cursor,
            effective_order,
            encode_cursor,
            reverse_order,
        )
        from alchemiq.repository.loading import apply_loaders
        from alchemiq.repository.pagination import CursorPage
        from alchemiq.runtime.session import session_scope

        order = effective_order(self.model, self._order)
        backward = before is not None
        token = before if backward else after

        stmt = self.compile().order_by(None).limit(None).offset(None)
        travel = reverse_order(order) if backward else order
        stmt = stmt.order_by(*_order_columns(self.model, travel))
        if token is not None:
            values = decode_cursor(token, self.model, order)
            stmt = stmt.where(build_seek(self.model, order, values, backward=backward))
        stmt = apply_loaders(
            stmt.limit(size + 1), self.model, self._select_related, self._prefetch_related
        )
        async with session_scope(write=False) as session:
            result = await session.execute(stmt)
            rows = list(result.scalars().unique().all())

        extra = len(rows) > size
        rows = rows[:size]
        if backward:
            rows.reverse()

        def enc(row: Any) -> str:
            return encode_cursor(self.model, order, row)

        if backward:
            has_prev = extra
            has_next = bool(rows)
            prev_cursor = enc(rows[0]) if (has_prev and rows) else None
            next_cursor = enc(rows[-1]) if rows else None
        else:
            has_next = extra
            has_prev = token is not None
            next_cursor = enc(rows[-1]) if (has_next and rows) else None
            prev_cursor = enc(rows[0]) if (has_prev and rows) else None

        return CursorPage(
            items=rows,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
            has_next=has_next,
            has_prev=has_prev,
        )

    def _own_where(self) -> Any:
        from sqlalchemy import and_

        from alchemiq.query.compiler import compile_q

        clauses = [compile_q(q, self.model) for q in self._where]  # join_ctx=None -> own cols
        predicate = deleted_predicate(self.model, self._deleted)
        if predicate is not None:
            clauses.append(predicate)
        return and_(*clauses) if clauses else None

    async def update(self, **changes: Any) -> int:
        """Execute a set-based ``UPDATE`` on own-column filters. Returns rowcount.

        :raises QueryError: if no filter is set; use :meth:`.QuerySet.update_all` for
            an unguarded full-table update.

        .. note::

            The automatic soft-delete predicate does not count as a user filter.
        """
        from alchemiq.exceptions import QueryError

        if not self._where:
            raise QueryError(
                "update() requires at least one filter; call .filter() first "
                "(use update_all() to update every row)"
            )
        return await self._update_impl(**changes)

    async def update_all(self, **changes: Any) -> int:
        """Execute a SET-BASED UPDATE over EVERY matching row (no user filter required).

        The explicit, lexically-distinct full-table escape hatch - :meth:`update` refuses
        an unfiltered call so a missing ``.filter()`` cannot silently rewrite the table.
        Still honors the current deleted-mode (default EXCLUDE skips tombstones).
        """
        return await self._update_impl(**changes)

    async def _update_impl(self, **changes: Any) -> int:
        from sqlalchemy import update as sa_update
        from sqlalchemy.engine import CursorResult

        from alchemiq.runtime.session import session_scope

        _where = self._own_where()
        stmt = sa_update(self.model)
        if _where is not None:
            stmt = stmt.where(_where)
        stmt = stmt.values(**changes)
        async with session_scope(write=True) as session:
            result = cast(
                CursorResult[Any],
                await session.execute(stmt.execution_options(synchronize_session=False)),
            )
            if self._cache is not None:
                from alchemiq.cache import ops
                from alchemiq.runtime.post_commit import enqueue_post_commit

                cache, model = self._cache, self.model
                enqueue_post_commit(lambda: ops.invalidate_model(cache, model))
            return int(result.rowcount)

    async def delete(self) -> int:
        """Execute a set-based ``DELETE`` on own-column filters. Returns rowcount.

        On a soft-delete model this stamps ``deleted_at`` (an ``UPDATE``) instead
        of a physical ``DELETE``.

        :raises QueryError: if no filter is set; use :meth:`.QuerySet.delete_all` for
            an unguarded full-table delete.
        """
        from alchemiq.exceptions import QueryError

        if not self._where:
            raise QueryError(
                "delete() requires at least one filter; call .filter() first "
                "(use delete_all() to delete every row)"
            )
        return await self._delete_impl()

    async def delete_all(self) -> int:
        """Execute a SET-BASED DELETE over EVERY matching row (no user filter required).

        Soft-delete models stamp ``deleted_at``; others physically DELETE. The explicit
        full-table escape hatch - :meth:`delete` refuses an unfiltered call. Honors the
        current deleted-mode (default EXCLUDE skips tombstones).
        """
        return await self._delete_impl()

    async def _delete_impl(self) -> int:
        from sqlalchemy import delete as sa_delete
        from sqlalchemy import update as sa_update
        from sqlalchemy.engine import CursorResult

        from alchemiq.runtime.session import session_scope

        _where = self._own_where()
        if is_soft_delete(self.model):
            from datetime import UTC, datetime

            stmt: Any = sa_update(self.model)
            if _where is not None:
                stmt = stmt.where(_where)
            stmt = stmt.values(deleted_at=datetime.now(UTC))
        else:
            stmt = sa_delete(self.model)
            if _where is not None:
                stmt = stmt.where(_where)
        async with session_scope(write=True) as session:
            result = cast(
                CursorResult[Any],
                await session.execute(stmt.execution_options(synchronize_session=False)),
            )
            if self._cache is not None:
                from alchemiq.cache import ops
                from alchemiq.runtime.post_commit import enqueue_post_commit

                cache, model = self._cache, self.model
                enqueue_post_commit(lambda: ops.invalidate_model(cache, model))
            return int(result.rowcount)

    async def hard_delete(self) -> int:
        """Execute a physical SET-BASED DELETE on own-column filters. Returns rowcount.

        Bypasses soft-delete: the rows are physically removed. Honors the current
        deleted-mode (default EXCLUDE purges live rows; ``only_deleted().hard_delete()``
        purges tombstones; ``with_deleted().hard_delete()`` purges both).
        """
        from sqlalchemy import delete as sa_delete
        from sqlalchemy.engine import CursorResult

        from alchemiq.exceptions import QueryError
        from alchemiq.runtime.session import session_scope

        if not self._where:
            raise QueryError("hard_delete() requires at least one filter; call .filter() first")
        stmt = sa_delete(self.model).where(self._own_where())
        async with session_scope(write=True) as session:
            result = cast(
                CursorResult[Any],
                await session.execute(stmt.execution_options(synchronize_session=False)),
            )
            if self._cache is not None:
                from alchemiq.cache import ops
                from alchemiq.runtime.post_commit import enqueue_post_commit

                cache, model = self._cache, self.model
                enqueue_post_commit(lambda: ops.invalidate_model(cache, model))
            return int(result.rowcount)

    async def last(self) -> Any | None:
        """Return the last row according to the current ordering.

        If an ``order_by`` is set, each field's direction is reversed (``-``
        prefix toggled).  If no ordering is set, falls back to descending PK.
        Delegates to :meth:`first` on the reversed clone.
        """
        if self._order:
            reversed_order = tuple(f[1:] if f.startswith("-") else f"-{f}" for f in self._order)
            qs = self._clone(order=reversed_order)
        else:
            qs = self._clone(order=(f"-{pk_name(self.model)}",))
        return await qs.first()
