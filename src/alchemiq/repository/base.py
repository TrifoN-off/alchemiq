"""Repository - the primary consumer-facing CRUD/query façade for alchemiq models."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar, cast, get_args, get_origin

from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from alchemiq.exceptions import ConcurrentModificationError, ConfigError, NotFoundError
from alchemiq.query.queryset import QuerySet, pk_name
from alchemiq.query.soft_delete import INCLUDE, is_soft_delete, is_versioned
from alchemiq.runtime.session import session_scope
from alchemiq.runtime.soft_delete_filter import DELETED_MODE_OPTION
from alchemiq.signals.registry import dispatch

if TYPE_CHECKING:
    from alchemiq.query.aggregates import Aggregate
    from alchemiq.repository.pagination import CursorPage, Page

M = TypeVar("M")


def _assert_version(model: type, obj: Any, expected: int, *, pk: Any) -> None:
    if not is_versioned(model):
        raise ConfigError(f"{model.__name__} is not versioned; expected_version is unavailable")
    current = obj._version
    if current != expected:
        raise ConcurrentModificationError(
            f"{model.__name__} pk={pk!r}: expected version {expected}, found {current}"
        )


async def _flush_or_conflict(session: AsyncSession, model: type, pk: Any) -> None:
    """Flush, translating SQLAlchemy's StaleDataError into ConcurrentModificationError."""
    try:
        await session.flush()
    except StaleDataError as e:
        raise ConcurrentModificationError(
            f"{model.__name__} with pk {pk!r} was modified concurrently"
        ) from e


class Repository(Generic[M]):  # noqa: UP046
    """Data-access surface for one model.

    Instantiate ad-hoc with ``Repository(Model)`` or subclass to attach behaviour:

    E.g.::

        # ad-hoc (no subclass)
        users = Repository(User)
        user = await users.create(name="Ada", email="ada@x.io")

        # subclass with cache
        class UserRepository(Repository[User]):
            cache = True
            cache_ttl = 300

        repo = UserRepository()
        user = await repo.get(1)
        await repo.update(1, name="Ada Lovelace")

    The repository delegates query building to :class:`.QuerySet` and write operations to
    SQLAlchemy sessions managed by :class:`.UnitOfWork` (or its own ``session_scope``).
    """

    model: type[M]
    cache: Any = False
    cache_ttl: int | None = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for base in getattr(cls, "__orig_bases__", ()):
            if get_origin(base) is Repository:
                args = get_args(base)
                if args and isinstance(args[0], type):
                    cls.model = args[0]
                    break

    def __init__(
        self,
        model: type[M] | None = None,
        *,
        cache: Any = None,
        cache_ttl: int | None = None,
    ) -> None:
        resolved = model if model is not None else getattr(type(self), "model", None)
        if resolved is None:
            raise TypeError(
                "Repository needs a model: call Repository(Model) or subclass Repository[Model]"
            )
        self.model = resolved
        if cache is not None:
            self.cache = cache
        if cache_ttl is not None:
            self.cache_ttl = cache_ttl

    def _resolve_cache(self) -> Any:
        from alchemiq.cache.backend import get_cache

        c = self.cache
        if c is False or c is None:
            return None
        if c is True:
            backend = get_cache()
            if backend is None:
                raise ConfigError(
                    f"{type(self).__name__} sets cache=True but configure_cache() was not called"
                )
            return backend
        return c

    def _effective_ttl(self, cache: Any) -> int:
        return self.cache_ttl if self.cache_ttl is not None else cache.default_ttl

    def _qs(self) -> QuerySet:
        return QuerySet(self.model, cache=self._resolve_cache(), cache_ttl=self.cache_ttl)

    def filter(self, *args: Any, **lookups: Any) -> QuerySet:
        """Return a QuerySet filtered by the given lookup expressions."""
        return self._qs().filter(*args, **lookups)

    def exclude(self, *args: Any, **lookups: Any) -> QuerySet:
        """Return a QuerySet excluding rows matching the given lookup expressions."""
        return self._qs().exclude(*args, **lookups)

    def order_by(self, *fields: str) -> QuerySet:
        """Return a QuerySet ordered by *fields* (prefix ``-`` for descending)."""
        return self._qs().order_by(*fields)

    def limit(self, n: int) -> QuerySet:
        """Return a QuerySet capped at *n* rows."""
        return self._qs().limit(n)

    def offset(self, n: int) -> QuerySet:
        """Return a QuerySet starting at row *n* (0-based)."""
        return self._qs().offset(n)

    def distinct(self) -> QuerySet:
        """Return a QuerySet that emits a SELECT DISTINCT."""
        return self._qs().distinct()

    def only(self, *fields: str) -> QuerySet:
        """Return a QuerySet that loads only the named columns (deferred load for others)."""
        return self._qs().only(*fields)

    def select_related(self, *names: str) -> QuerySet:
        """Return a QuerySet that JOIN-loads the named relationships (one SQL query)."""
        return self._qs().select_related(*names)

    def prefetch_related(self, *names: str) -> QuerySet:
        """Return a QuerySet that SELECT-IN-loads the named relationships (extra query per rel)."""
        return self._qs().prefetch_related(*names)

    def with_deleted(self) -> QuerySet:
        """Return a QuerySet that includes soft-deleted rows alongside live ones."""
        return self._qs().with_deleted()

    def only_deleted(self) -> QuerySet:
        """Return a QuerySet scoped to soft-deleted (tombstoned) rows only."""
        return self._qs().only_deleted()

    async def get(self, *args: Any, **lookups: Any) -> M:
        """Fetch exactly one row matching *lookups*.

        E.g.::

            user = await users.get(id=1)
            user = await users.get(email="ada@x.io")

        :param lookups: column-equality filters; arbitrary SQLAlchemy expressions accepted
            as positional *args*.
        :return: the matched model instance.
        :raises NotFoundError: if no row matches.
        :raises MultipleResultsFound: if more than one row matches.
        """
        cache = self._resolve_cache()
        pk = pk_name(self.model)
        if cache is not None and not args and set(lookups) == {pk}:
            from alchemiq.cache import ops

            async def _fetch_get() -> M:
                return await QuerySet(self.model).get(**lookups)  # cache-free fetch

            return await ops.read_obj(
                self.model, cache, self._effective_ttl(cache), lookups[pk], _fetch_get
            )
        return await self._qs().get(*args, **lookups)

    async def get_or_none(self, *args: Any, **lookups: Any) -> M | None:
        """Fetch the row matching *lookups*, or ``None`` if absent.

        E.g.::

            user = await users.get_or_none(id=42)
            if user is None:
                ...  # not found

        :param lookups: column-equality filters; arbitrary SQLAlchemy expressions accepted
            as positional *args*.
        :return: the matched model instance, or ``None``.
        :raises MultipleResultsFound: if more than one row matches.
        """
        cache = self._resolve_cache()
        pk = pk_name(self.model)
        if cache is not None and not args and set(lookups) == {pk}:
            from alchemiq.cache import ops

            async def _fetch_get_or_none() -> M:
                return await QuerySet(self.model).get(**lookups)

            try:
                return await ops.read_obj(
                    self.model, cache, self._effective_ttl(cache), lookups[pk], _fetch_get_or_none
                )
            except NotFoundError:
                return None
        return await self._qs().get_or_none(*args, **lookups)

    async def first(self) -> M | None:
        """Return the first row in the current ordering (``LIMIT 1``), or ``None`` if empty.

        With no ``order_by`` chained, no ``ORDER BY`` is emitted, so which row is "first" is
        database-defined; chain ``order_by`` for a deterministic result.

        .. note::
            There is no default ``ORDER BY``. For a stable "first" result, always chain
            ``order_by`` before calling this method.
        """
        return await self._qs().first()

    async def last(self) -> M | None:
        """Return the last row in the current ordering, or ``None`` if empty.

        Reverses each chained ``order_by`` direction; with no ordering, falls back to
        descending primary key.
        """
        return await self._qs().last()

    async def all(self) -> list[M]:
        """Return all rows as a list."""
        return await self._qs().all()

    async def exists(self, *args: Any, **lookups: Any) -> bool:
        """Return ``True`` if at least one row matches the optional *lookups*."""
        qs = self._qs().filter(*args, **lookups) if (args or lookups) else self._qs()
        return await qs.exists()

    async def count(self, *args: Any, **lookups: Any) -> int:
        """Return the number of rows matching the optional *lookups*."""
        qs = self._qs().filter(*args, **lookups) if (args or lookups) else self._qs()
        return await qs.count()

    async def aggregate(self, **exprs: Aggregate) -> dict[str, Any]:
        """Compute aggregate expressions (Count, Sum, Avg, Min, Max) over the table."""
        return await self._qs().aggregate(**exprs)

    async def explain(
        self, *, analyze: bool = False, format: Literal["text", "json"] = "text"
    ) -> str | list[Any]:
        """Return the query plan for the current QuerySet (PostgreSQL only)."""
        return await self._qs().explain(analyze=analyze, format=format)

    async def paginate(self, page: int = 1, size: int = 20) -> Page[M]:
        """Return a ``Page`` for the given 1-based *page* number and *size*."""
        return await self._qs().paginate(page=page, size=size)

    async def cursor_paginate(
        self, *, size: int = 20, after: str | None = None, before: str | None = None
    ) -> CursorPage[M]:
        """Return a ``CursorPage`` navigating forward (*after*) or backward (*before*)."""
        return await self._qs().cursor_paginate(size=size, after=after, before=before)

    async def create(self, **values: Any) -> M:
        """Instantiate the model from *values*, persist it, and return the new instance."""
        return await self.add(self.model(**values))

    async def add(self, obj: M) -> M:
        """Persist an already-constructed model instance and return it (fires pre/post_create)."""
        cache = self._resolve_cache()
        async with session_scope(write=True) as session:
            session.add(obj)
            await dispatch("pre_create", self.model, obj)
            await session.flush()
            await dispatch("post_create", self.model, obj)
            if cache is not None:
                from alchemiq.cache import ops
                from alchemiq.runtime.post_commit import enqueue_post_commit

                model = self.model
                enqueue_post_commit(lambda: ops.bump_version(cache, model))
            return obj

    async def update(self, id: Any, *, expected_version: int | None = None, **changes: Any) -> M:
        """Apply ``changes`` to the row ``id`` and return the refreshed instance.

        Executes within the ambient :class:`.UnitOfWork` if one is active, otherwise in
        its own autocommit transaction.  Fires the ``pre_update`` / ``post_update``
        signals around the flush.

        E.g.::

            user = await users.update(3, age=26)

            # optimistic concurrency control:
            version = alchemiq.version_of(user)
            await users.update(3, expected_version=version, name="Ada")

        :param id: primary key of the row to update.
        :param expected_version: when given, the row's ``_version`` must equal this value
            or :class:`.ConcurrentModificationError` is raised and nothing is written.
            Read it with :func:`.version_of`.
        :param changes: ``column=value`` pairs to assign; each is validated as on assignment.
        :return: the refreshed model instance.
        :raises NotFoundError: if no row with ``id`` exists.
        :raises ConcurrentModificationError: if ``expected_version`` did not match,
            or a concurrent flush detected a stale version.

        .. seealso:: :meth:`.Repository.bulk_update` - set-based, no per-row signals.
        """
        cache = self._resolve_cache()
        async with session_scope(write=True) as session:
            obj = await session.get(self.model, id)
            if obj is None:
                raise NotFoundError(f"{self.model.__name__} with pk {id!r} not found")
            if expected_version is not None:
                _assert_version(self.model, obj, expected_version, pk=id)
            for key, value in changes.items():
                setattr(obj, key, value)  # assignment triggers eager field validation
            await dispatch("pre_update", self.model, obj)
            await _flush_or_conflict(session, self.model, id)
            await dispatch("post_update", self.model, obj)
            if cache is not None:
                from alchemiq.cache import ops
                from alchemiq.runtime.post_commit import enqueue_post_commit

                model = self.model
                enqueue_post_commit(lambda: ops.invalidate_row(cache, model, id))
            return obj

    async def delete(self, id: Any, *, expected_version: int | None = None) -> None:
        """Delete the row identified by ``id``.

        Soft-delete models stamp ``deleted_at`` (no physical row removal); others issue a
        physical ``DELETE``.  Fires the ``pre_delete`` / ``post_delete`` signals in both
        cases.  Supports optimistic locking via ``expected_version``.

        E.g.::

            # physical delete (non-soft-delete model)
            await posts.delete(5)

            # optimistic concurrency control on a soft-delete model
            await repo.delete(20, expected_version=1)

        :param id: primary key of the row to delete.
        :param expected_version: when given, the row's ``_version`` must equal this value
            or :class:`.ConcurrentModificationError` is raised and nothing is written.
        :raises NotFoundError: if no live row with ``id`` exists (for soft-delete models,
            an already-deleted row also counts as not found).
        :raises ConcurrentModificationError: if ``expected_version`` did not match,
            or a concurrent flush detected a stale version.

        .. note::
            For soft-delete models, ``delete()`` stamps ``deleted_at`` and leaves the
            physical row intact.  Use :meth:`.Repository.hard_delete` to remove it
            unconditionally, or :meth:`.Repository.restore` to reverse the deletion.
        """
        cache = self._resolve_cache()
        async with session_scope(write=True) as session:
            obj = await session.get(self.model, id)
            if is_soft_delete(self.model):
                if obj is None or obj.deleted_at is not None:  # ty: ignore[unresolved-attribute]
                    raise NotFoundError(f"{self.model.__name__} with pk {id!r} not found")
                if expected_version is not None:
                    _assert_version(self.model, obj, expected_version, pk=id)
                await dispatch("pre_delete", self.model, obj)
                obj.deleted_at = datetime.now(UTC)  # ty: ignore[unresolved-attribute,invalid-assignment]
                await _flush_or_conflict(session, self.model, id)
                await dispatch("post_delete", self.model, obj)
                if cache is not None:
                    from alchemiq.cache import ops
                    from alchemiq.runtime.post_commit import enqueue_post_commit

                    model = self.model
                    enqueue_post_commit(lambda: ops.invalidate_row(cache, model, id))
                return
            if obj is None:
                raise NotFoundError(f"{self.model.__name__} with pk {id!r} not found")
            if expected_version is not None:
                _assert_version(self.model, obj, expected_version, pk=id)
            await dispatch("pre_delete", self.model, obj)
            await session.delete(obj)
            await _flush_or_conflict(session, self.model, id)
            await dispatch("post_delete", self.model, obj)
            if cache is not None:
                from alchemiq.cache import ops
                from alchemiq.runtime.post_commit import enqueue_post_commit

                model = self.model
                enqueue_post_commit(lambda: ops.invalidate_row(cache, model, id))

    async def restore(self, id: Any) -> M:
        """Clear ``deleted_at`` on a soft-deleted row, returning it to the live set.

        Fires the ``pre_update`` / ``post_update`` signals around the flush.

        E.g.::

            await repo.restore(1)

        :param id: primary key of the tombstoned row to restore.
        :return: the restored model instance.
        :raises ConfigError: if the model does not have soft-delete enabled.
        :raises NotFoundError: if no tombstone (soft-deleted row) with ``id`` exists.
        """
        if not is_soft_delete(self.model):
            raise ConfigError(f"{self.model.__name__} is not soft-delete; restore() is unavailable")
        cache = self._resolve_cache()
        async with session_scope(write=True) as session:
            obj = await session.get(
                self.model, id, execution_options={DELETED_MODE_OPTION: INCLUDE}
            )
            if obj is None or obj.deleted_at is None:  # ty: ignore[unresolved-attribute]
                raise NotFoundError(f"{self.model.__name__} tombstone with pk {id!r} not found")
            await dispatch("pre_update", self.model, obj)
            obj.deleted_at = None  # ty: ignore[unresolved-attribute,invalid-assignment]
            await _flush_or_conflict(session, self.model, id)
            await dispatch("post_update", self.model, obj)
            if cache is not None:
                from alchemiq.cache import ops
                from alchemiq.runtime.post_commit import enqueue_post_commit

                model = self.model
                enqueue_post_commit(lambda: ops.invalidate_row(cache, model, id))
            return obj

    async def hard_delete(self, id: Any) -> None:
        """Physically DELETE the row identified by ``id``, regardless of soft-delete status.

        Bypasses the soft-delete predicate: removes the physical row even if it has a
        ``deleted_at`` stamp.  Fires the ``pre_delete`` / ``post_delete`` signals.

        E.g.::

            await repo.hard_delete(31)

        :param id: primary key of the row to delete (live or tombstoned).
        :raises NotFoundError: if no row with ``id`` exists (live or tombstoned).

        .. seealso:: :meth:`.Repository.delete` - respects soft-delete; stamps ``deleted_at``
            instead of issuing ``DELETE``.
        """
        cache = self._resolve_cache()
        async with session_scope(write=True) as session:
            obj = await session.get(
                self.model, id, execution_options={DELETED_MODE_OPTION: INCLUDE}
            )
            if obj is None:
                raise NotFoundError(f"{self.model.__name__} with pk {id!r} not found")
            await dispatch("pre_delete", self.model, obj)
            await session.delete(obj)
            await _flush_or_conflict(session, self.model, id)
            await dispatch("post_delete", self.model, obj)
            if cache is not None:
                from alchemiq.cache import ops
                from alchemiq.runtime.post_commit import enqueue_post_commit

                model = self.model
                enqueue_post_commit(lambda: ops.invalidate_row(cache, model, id))

    async def bulk_create(self, objs: Iterable[M]) -> list[M]:
        """Persist multiple instances in a single flush and return the inserted objects.

        Fires no per-row signals and writes no outbox entries.  Prefer this over repeated
        :meth:`.Repository.create` calls when inserting many rows at once.

        E.g.::

            rows = await repo.bulk_create([
                Item(id=10, name="x", age=1),
                Item(id=11, name="y", age=2),
            ])

        :param objs: iterable of model instances to insert.
        :return: the list of inserted objects (same order as input); ``[]`` if *objs* is
            empty.

        .. seealso:: :meth:`.Repository.bulk_upsert` - idempotent ``INSERT ... ON CONFLICT``.
        """
        items = list(objs)
        if not items:
            return []
        cache = self._resolve_cache()
        async with session_scope(write=True) as session:
            session.add_all(items)
            await session.flush()
            if cache is not None:
                from alchemiq.cache import ops
                from alchemiq.runtime.post_commit import enqueue_post_commit

                model = self.model
                enqueue_post_commit(lambda: ops.bump_version(cache, model))
            return items

    async def bulk_upsert(
        self,
        objs: Iterable[M],
        *,
        conflict: Sequence[str] | None = None,
        update_fields: Sequence[str] | None = None,
        ignore_conflicts: bool = False,
    ) -> int:
        """Idempotent batch ``INSERT ... ON CONFLICT`` (PostgreSQL / SQLite).

        Returns the affected rowcount.

        ``conflict`` defaults to the PK column(s); ``update_fields`` defaults to all sent
        non-conflict columns.  ``ignore_conflicts=True`` emits ``DO NOTHING`` instead of
        ``DO UPDATE``.  Fires no signals and writes no outbox (like all bulk operations).
        Operates on physical rows - the soft-delete predicate is not applied.

        E.g.::

            n = await repo.bulk_upsert([User(id=1, email="a@x.c", name="A")])

            # override the conflict column:
            await repo.bulk_upsert(
                [User(id=1, email="dup@x.c", name="first")],
                conflict=["email"],
            )

        :param objs: iterable of model instances to upsert; empty -> returns ``0``.
        :param conflict: columns that identify a conflict; defaults to the primary key.
        :param update_fields: columns to overwrite on conflict; defaults to all non-conflict
            columns present in the batch.
        :param ignore_conflicts: when ``True``, conflicting rows are silently skipped
            (``DO NOTHING``); ``update_fields`` is ignored.
        :return: number of rows affected (inserted + updated).

        .. seealso:: :meth:`.Repository.bulk_create` - plain insert without conflict handling.
        """
        items = list(objs)
        if not items:
            return 0
        from sqlalchemy.engine import CursorResult

        from alchemiq._internal.dialect import insert_for
        from alchemiq.repository.upsert import build_upsert
        from alchemiq.runtime.engine import require_engine

        cache = self._resolve_cache()
        stmt = build_upsert(
            self.model,
            items,
            conflict=conflict,
            update_fields=update_fields,
            ignore_conflicts=ignore_conflicts,
            insert_fn=insert_for(require_engine()),
        )
        async with session_scope(write=True) as session:
            result = cast(CursorResult[Any], await session.execute(stmt))
            if cache is not None:
                from alchemiq.cache import ops
                from alchemiq.runtime.post_commit import enqueue_post_commit

                model = self.model
                enqueue_post_commit(lambda: ops.invalidate_model(cache, model))
            return int(result.rowcount)

    @staticmethod
    def _create_values(lookups: dict[str, Any], defaults: dict[str, Any] | None) -> dict[str, Any]:
        base = {k: v for k, v in lookups.items() if "__" not in k}
        return {**base, **(defaults or {})}

    async def get_or_create(
        self, defaults: dict[str, Any] | None = None, **lookups: Any
    ) -> tuple[M, bool]:
        """Fetch the row matching ``lookups``, or create it from ``lookups`` + ``defaults``.

        E.g.::

            obj, created = await repo.get_or_create(
                id=1, email="a@b.c", defaults={"name": "Ann"}
            )

        :param defaults: extra fields used only when creating (not matched against existing rows).
        :param lookups: column-equality filters that identify the row.
        :return: ``(obj, created)`` - ``True`` when a new row was inserted.

        .. warning::
            NOT atomic outside a :class:`.UnitOfWork`.  The lookup and the create run in
            separate transactions, so a concurrent insert between them can surface an
            integrity error.  Wrap in ``async with UnitOfWork():`` for atomicity.
        """
        existing = await self.get_or_none(**lookups)
        if existing is not None:
            return existing, False
        obj = await self.create(**self._create_values(lookups, defaults))
        return obj, True

    async def update_or_create(
        self, defaults: dict[str, Any] | None = None, **lookups: Any
    ) -> tuple[M, bool]:
        """Update the row matching ``lookups`` (with ``defaults``), or create it.

        E.g.::

            obj, created = await repo.update_or_create(id=2, defaults={"name": "new"})

        :param defaults: fields to write when updating or creating.
        :param lookups: column-equality filters that identify the row.
        :return: ``(obj, created)`` - ``True`` when a new row was inserted.

        .. warning::
            Best-effort atomic outside a :class:`.UnitOfWork`.  If the matched row is
            concurrently deleted between the lookup and the update, the
            ``NotFoundError`` is caught and the call falls through to ``create()``.
            Wrap in ``async with UnitOfWork():`` for true atomicity.
        """
        existing = await self.get_or_none(**lookups)
        if existing is not None:
            try:
                updated = await self.update(
                    getattr(existing, pk_name(self.model)), **(defaults or {})
                )
                return updated, False
            except NotFoundError:
                pass  # row vanished between lookup and update - fall through to create
        obj = await self.create(**self._create_values(lookups, defaults))
        return obj, True

    async def bulk_update(self, objs: Iterable[M], fields: Sequence[str]) -> int:
        """Bulk UPDATE by PK for the given ``fields``. Returns ``len(items)``, not DB rowcount.

        Uses SQLAlchemy's bulk-update-by-PK path: a single ``UPDATE`` per batch rather
        than one flush per row.  Objects must have PK + field attributes accessible (no
        ``DetachedInstanceError``) - prefer calling inside a :class:`.UnitOfWork`.

        E.g.::

            n = await repo.bulk_update(rows, fields=["age"])

        :param objs: iterable of model instances whose PKs identify the rows to update.
        :param fields: column names to write from each object.
        :return: number of objects submitted (``len(items)``); rows absent from the DB are
            silently skipped by SQLAlchemy's bulk path - do not rely on this count to
            detect missing PKs.

        .. seealso:: :meth:`.Repository.bulk_upsert` - insert-or-update in one statement.

        .. warning::
            Bypasses the optimistic-lock version check and increment (set-based, no
            per-row ORM flush).  Fires no per-row signals.
        """
        items = list(objs)
        if not items:
            return 0
        cache = self._resolve_cache()
        pk = pk_name(self.model)
        async with session_scope(write=True) as session:
            # Read attrs inside the scope so the executing session is alive during access.
            mappings = [{pk: getattr(o, pk), **{f: getattr(o, f) for f in fields}} for o in items]
            await session.execute(sa_update(self.model), mappings)
            if cache is not None:
                from alchemiq.runtime.post_commit import enqueue_post_commit

                model = self.model
                pks = [getattr(o, pk) for o in items]
                enqueue_post_commit(lambda: _invalidate_rows(cache, model, pks))
            return len(items)

    async def update_all(self, **changes: Any) -> int:
        """Apply ``changes`` to every row without requiring a preceding ``filter()``.

        Explicit full-table escape hatch: ``filter().update()`` refuses an unfiltered call.
        That filtered variant limits lookups to own columns; relationship traversal raises
        ``QueryError``.  Bypasses the optimistic-lock version check and increment
        (set-based, no per-row ORM flush).  Fires no per-row signals.

        :param changes: ``column=value`` pairs to assign across all rows.
        :return: number of rows updated.

        .. warning::
            This method updates **every row in the table**.  There is no ``WHERE`` clause
            unless you call ``filter().update()`` instead.  Double-check that a full-table
            update is intentional before using this method.
        """
        return await self._qs().update_all(**changes)

    async def delete_all(self) -> int:
        """Delete every row without requiring a preceding ``filter()``.

        Explicit full-table escape hatch: ``filter().delete()`` refuses an unfiltered call.
        That filtered variant limits lookups to own columns; relationship traversal raises
        ``QueryError``.  Soft-delete models stamp ``deleted_at``; others issue a
        physical ``DELETE``.  Bypasses the optimistic-lock version check and increment
        (set-based, no per-row ORM flush).  Fires no per-row signals.

        E.g.::

            n = await repo.delete_all()

        :return: number of rows deleted (or soft-deleted).

        .. warning::
            This method deletes **every row in the table**.  There is no ``WHERE`` clause
            unless you call ``filter().delete()`` instead.  Double-check that a full-table
            delete is intentional before using this method.
        """
        return await self._qs().delete_all()

    async def cache_clear(self) -> None:
        """Invalidate the entire model cache (version bump + flush precise object keys)."""
        cache = self._resolve_cache()
        if cache is None:
            return
        from alchemiq.cache import ops

        await ops.invalidate_model(cache, self.model)

    async def cache_evict(self, pk: Any) -> None:
        """Invalidate one object (drop its precise key + bump version)."""
        cache = self._resolve_cache()
        if cache is None:
            return
        from alchemiq.cache import ops

        await ops.invalidate_row(cache, self.model, pk)


async def _invalidate_rows(cache: Any, model: type, pks: list[Any]) -> None:
    from alchemiq.cache import keys, ops

    await ops.bump_version(cache, model)
    for pk in pks:
        await cache.delete(keys.obj_key(cache.namespace, model.__tablename__, pk))  # ty: ignore[unresolved-attribute]
