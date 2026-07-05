"""ClickHouseModel declarative base and subclass initialisation pipeline."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import DeclarativeBase

from alchemiq.clickhouse.engines import _Engine
from alchemiq.clickhouse.registry import ch_mapper_registry, ch_metadata
from alchemiq.exceptions import ConfigError
from alchemiq.model.meta_options import parse_meta
from alchemiq.model.pipeline import (
    install_descriptors,
    prepare_fields,
    register_validators,
)
from alchemiq.types.base import _MISSING, FieldType

_CAMEL = re.compile(r"(?<!^)(?=[A-Z])")


class _CHGenericField(FieldType):
    """Thin wrapper that delegates column_type() to ch_column_type(python_type).

    Used to inject CH-typed columns for bare python-type annotations (e.g. url: str)
    before the field pipeline runs, so the resulting mapped column carries a
    clickhouse_sqlalchemy type rather than a plain SQLAlchemy type.
    """

    def column_type(self) -> Any:
        from alchemiq.clickhouse.types import ch_column_type  # ty: ignore[unresolved-import]

        return ch_column_type(self.python_type)


def _inject_ch_bare_annotations(cls: type) -> None:
    """For each bare python-type annotation with no value-slot, inject a _CHGenericField.

    This runs before prepare_fields() so resolve_field() takes branch 1
    (configured FieldType instance wins) and builds a CH-typed mapped_column.
    """
    import datetime as dt
    from decimal import Decimal
    from uuid import UUID

    ch_mappable: frozenset[type] = frozenset(
        {int, str, float, bool, dt.datetime, dt.date, Decimal, UUID}
    )

    own_annotations = {
        name: ann for name, ann in cls.__annotations__.items() if not name.startswith("__")
    }
    for name, ann in own_annotations.items():
        # Skip if a value-slot is already set (FieldType, default, etc.)
        if cls.__dict__.get(name, _MISSING) is not _MISSING:
            continue
        if ann in ch_mappable:
            f = _CHGenericField(python_type=ann)
            setattr(cls, name, f)


def _mark_order_by_as_pk(cls: type, engine: _Engine) -> None:
    """Mark ORDER BY columns as SA primary key columns and keep the alchemiq layer in sync.

    SQLAlchemy's DeclarativeBase requires at least one PK column for mapping.
    ClickHouse tables have no traditional PK, so we designate ORDER BY columns as the SA-level PK.
    This does not affect DDL (the DDL compiler emits the actual ENGINE clause) - it only satisfies
    the SA mapper.

    Two edge cases handled:

    - Expression ORDER BY (e.g. ``order_by="toYYYYMM(event_time)"``): expressions are not mapped
      column names, so none would resolve.  We fall back to the first field in
      ``__alchemiq_fields__`` as a surrogate SA PK (CH has no real PK; SA just needs one).
    - Layer sync: ``FieldType.config`` is a frozen dataclass.  We use ``dataclasses.replace``
      to produce an updated copy and ``object.__setattr__`` to write through the freeze so that
      ``pk_name(model)`` (which reads ``field.config.primary_key``) returns the correct name.
    """
    import dataclasses

    # Normalise str -> single-element tuple so the loop is uniform.
    order_cols: tuple[str, ...] = (
        (engine.order_by,) if isinstance(engine.order_by, str) else tuple(engine.order_by)
    )

    fields: dict[str, Any] = cls.__alchemiq_fields__  # ty: ignore[unresolved-attribute]

    # Collect only entries that correspond to a mapped column (not SQL expressions).
    resolved: list[str] = [name for name in order_cols if name in fields]

    if not resolved:
        # All ORDER BY entries are expressions (e.g. toYYYYMM(event_time)).
        # Pick the first field as a surrogate SA PK so the mapper can proceed.
        # ClickHouse has no real PK constraint - this is purely SA bookkeeping.
        resolved = [next(iter(fields))]

    for name in resolved:
        mc = cls.__dict__.get(name)
        if mc is not None and hasattr(mc, "column"):
            mc.column.primary_key = True

        # Keep the alchemiq FieldType.config in sync so pk_name(model) works correctly.
        field = fields.get(name)
        if field is not None and not field.config.primary_key:
            object.__setattr__(field, "config", dataclasses.replace(field.config, primary_key=True))


def _inject_soft_delete_fields(cls: type) -> None:
    """Inject is_deleted, _version, deleted_at columns for soft-delete ClickHouse models.

    Must be called AFTER cls.__alchemiq_ch_engine__ is set and BEFORE prepare_fields(),
    so the pipeline resolves these to CH-typed mapped columns. Records the injected names
    in __alchemiq_structural_injected__ so the shared _inject_structural guard treats them
    as framework-owned (not a user collision).
    """
    import datetime as dt

    from alchemiq.clickhouse.types import DateTime64, UInt8

    ann = dict(getattr(cls, "__annotations__", {}))
    injected: set[str] = set()
    if "is_deleted" not in ann:
        ann["is_deleted"] = int
        cls.is_deleted = UInt8(default=0)  # ty: ignore[unresolved-attribute]
        injected.add("is_deleted")
    if "_version" not in ann:
        ann["_version"] = dt.datetime
        cls._version = DateTime64(3, default=lambda: dt.datetime.now(dt.UTC))  # ty: ignore[unresolved-attribute]
        injected.add("_version")
    if "deleted_at" not in ann:
        ann["deleted_at"] = dt.datetime | None  # nullable DateTime64; value slot provides CH type
        cls.deleted_at = DateTime64(3, nullable=True, default=None)  # ty: ignore[unresolved-attribute]
        injected.add("deleted_at")
    cls.__annotations__ = ann
    cls.__alchemiq_structural_injected__ = frozenset(injected)  # ty: ignore[unresolved-attribute]


def _snake(name: str) -> str:
    # Preserve leading underscores (e.g. _PageView -> _page_view, not __page_view).
    leading = len(name) - len(name.lstrip("_"))
    prefix = name[:leading]
    rest = name[leading:]
    return prefix + _CAMEL.sub("_", rest).lower()


def ch_engine_of(model: type) -> _Engine:
    """Return the CH engine stored on *model* or raise ConfigError."""
    engine = getattr(model, "__alchemiq_ch_engine__", None)
    if engine is None:
        raise ConfigError(f"{model.__name__} has no Meta.engine")
    return engine


class ClickHouseModel(DeclarativeBase):
    """Annotation-first base for ClickHouse tables (separate metadata/registry).

    Declare fields like a normal alchemiq Model and set the table engine in ``Meta``.
    Every concrete subclass must provide ``Meta.engine`` (:class:`.MergeTree`,
    :class:`.ReplacingMergeTree`, or :class:`.AggregatingMergeTree`); omitting it
    raises ``ConfigError`` at class-definition time.  The engine in turn
    requires an ``order_by`` argument (a ``TypeError`` is raised without it) -
    ClickHouse has no implicit primary key, and the ORDER BY key is what the
    MergeTree family sorts and (for ``FINAL`` / soft-delete) collapses on.

    For soft-delete support, set ``Meta.soft_delete = True`` and use
    :class:`.ReplacingMergeTree` - alchemiq will inject ``is_deleted``,
    ``_version``, and ``deleted_at`` columns automatically.

    E.g.::

        import datetime as dt
        from alchemiq.clickhouse import ClickHouseModel, MergeTree, ReplacingMergeTree
        from alchemiq.clickhouse.types import DateTime64, UInt32

        class PageView(ClickHouseModel):
            event_time: dt.datetime = DateTime64(3)
            user_id: int = UInt32()
            class Meta:
                engine = MergeTree(order_by=("event_time", "user_id"))

        class Document(ClickHouseModel):
            key: int = UInt32()
            body: str
            class Meta:
                soft_delete = True
                engine = ReplacingMergeTree(order_by=("key",))

    .. note::

        ``ch_metadata`` and ``ch_mapper_registry`` are kept separate from the
        PostgreSQL registry so CH and PG models never share the same
        ``MetaData``.

    .. seealso:: :func:`.configure_clickhouse` - connect the process-global client.
    .. seealso:: :class:`.ClickHouseRepository` - read/write rows for this model.
    """

    __abstract__ = True
    registry = ch_mapper_registry
    metadata = ch_metadata

    def __init_subclass__(cls, **kwargs: Any) -> None:
        cls.__alchemiq_meta__ = parse_meta(cls)

        if cls.__dict__.get("__abstract__", False):
            super().__init_subclass__(**kwargs)
            return

        inner_meta = cls.__dict__.get("Meta")
        engine = getattr(inner_meta, "engine", None)
        if not isinstance(engine, _Engine):
            raise ConfigError(
                f"{cls.__name__}: ClickHouse models require Meta.engine "
                f"(MergeTree/ReplacingMergeTree/AggregatingMergeTree)"
            )
        cls.__alchemiq_ch_engine__ = engine

        if cls.__alchemiq_meta__.soft_delete:
            from dataclasses import replace as _dc_replace

            from alchemiq.clickhouse.engines import ReplacingMergeTree

            if not isinstance(engine, ReplacingMergeTree):
                raise ConfigError(
                    f"{cls.__name__}: Meta.soft_delete=True requires ReplacingMergeTree"
                )
            _inject_soft_delete_fields(cls)
            version = engine.version or "_version"
            cls.__alchemiq_ch_engine__ = _dc_replace(  # ty: ignore[unresolved-attribute]
                engine, version=version, is_deleted="is_deleted"
            )

        if "__tablename__" not in cls.__dict__:
            cls.__tablename__ = cls.__alchemiq_meta__.table_name or _snake(cls.__name__)

        # Inject CH-typed field instances for bare python-type annotations BEFORE
        # the pipeline runs, so prepare_fields resolves them to CH column types.
        _inject_ch_bare_annotations(cls)

        fields = prepare_fields(cls)

        # Mark ORDER BY columns as SA primary keys so the mapper can proceed.
        # ClickHouse has no traditional PK; this is SA bookkeeping only.
        _mark_order_by_as_pk(cls, engine)

        super().__init_subclass__(**kwargs)
        register_validators(cls, fields)
        install_descriptors(cls, fields)
