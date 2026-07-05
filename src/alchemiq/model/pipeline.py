"""prepare_fields - converts class annotations -> FieldType mapping and wires SQLAlchemy columns."""

from __future__ import annotations

import sys
import typing
from typing import Any

from sqlalchemy import CheckConstraint, UniqueConstraint, event
from sqlalchemy import Index as SAIndex
from sqlalchemy.orm import Mapped

from alchemiq._internal.annotations import NATIVE_RELATIONSHIP, _native_spec, resolve_field
from alchemiq.exceptions import ConfigError, ValidationError
from alchemiq.model.meta_options import Check as MetaCheck
from alchemiq.model.meta_options import Unique as MetaUnique
from alchemiq.types.base import _MISSING, FieldConfig, FieldType, _NativeField

_RESERVED = {"Meta", "metadata", "registry"}


def _inject_structural(cls: type) -> None:
    """Inject deleted_at / created_at / updated_at / _version annotations driven by MetaOptions.

    Must be called BEFORE get_type_hints so injected names land in own annotations.
    Sets both cls.__annotations__[name] = python_type and cls.<name> = FieldType instance
    so that prepare_fields picks them up via resolve_field branch 1.

    The framework owns these injected names whenever the corresponding Meta flag is on:
    a model may not BOTH set the flag AND declare the column itself - that raises
    ConfigError (fail loud, never silently prefer the user's field). A structural-named
    column WITHOUT its Meta flag is a normal user column and is left untouched.
    """
    meta = getattr(cls, "__alchemiq_meta__", None)
    if not (meta and (meta.soft_delete or meta.timestamps or meta.versioned)):
        return

    from alchemiq.types.temporal import CreatedAt, DateTimeTz, UpdatedAt

    existing: set[str] = set(cls.__annotations__)
    injected_by_framework: frozenset[str] = getattr(
        cls, "__alchemiq_structural_injected__", frozenset()
    )

    def _claim(name: str, flag: str) -> bool:
        """Decide whether to inject ``name`` now.

        True -> inject now; False -> a framework path already injected it;
        raise ConfigError -> genuine user collision.
        """
        if name not in existing:
            return True
        if name in injected_by_framework:
            return False
        raise ConfigError(
            f"{cls.__name__} declares `{name}` but also sets Meta.{flag}; remove one - "
            f"Meta.{flag} injects `{name}` automatically."
        )

    if meta.soft_delete and _claim("deleted_at", "soft_delete"):
        f = DateTimeTz(nullable=True)
        cls.__annotations__["deleted_at"] = f.python_type
        cls.deleted_at = f  # ty: ignore[unresolved-attribute]

    if meta.timestamps:
        if _claim("created_at", "timestamps"):
            f_ca = CreatedAt()
            cls.__annotations__["created_at"] = f_ca.python_type
            cls.created_at = f_ca  # ty: ignore[unresolved-attribute]
        if _claim("updated_at", "timestamps"):
            f_ua = UpdatedAt()
            cls.__annotations__["updated_at"] = f_ua.python_type
            cls.updated_at = f_ua  # ty: ignore[unresolved-attribute]

    if meta.versioned and _claim("_version", "versioned"):
        from alchemiq.types.numeric import Version

        f_v = Version()
        cls.__annotations__["_version"] = f_v.python_type
        cls._version = f_v  # ty: ignore[unresolved-attribute]


def _apply_table_args(cls: type) -> None:
    """Build __table_args__ from MetaOptions indexes, constraints, and schema.

    Merges with any user-defined __table_args__ already on the class.
    Must be called BEFORE super().__init_subclass__() so SQLAlchemy reads it during mapping.
    """
    meta = getattr(cls, "__alchemiq_meta__", None)
    if meta is None:
        return
    tablename: str = cls.__tablename__  # ty: ignore[unresolved-attribute]
    new_args: list[Any] = []
    schema_dict: dict[str, Any] = {}

    for idx in meta.indexes:
        col_str = "_".join(idx.columns)
        unique_prefix = "uq" if idx.unique else "ix"
        name = f"{unique_prefix}_{tablename}_{col_str}"
        new_args.append(SAIndex(name, *idx.columns, unique=idx.unique))

    for constraint in meta.constraints:
        if isinstance(constraint, MetaUnique):
            new_args.append(UniqueConstraint(*constraint.columns))
        elif isinstance(constraint, MetaCheck):
            new_args.append(CheckConstraint(constraint.expression))

    if meta.schema:
        schema_dict["schema"] = meta.schema

    if not new_args and not schema_dict:
        return

    existing = cls.__dict__.get("__table_args__")
    if existing is None:
        # No user-defined args; set fresh.
        if schema_dict:
            cls.__table_args__ = tuple(new_args) + (schema_dict,)  # ty: ignore[unresolved-attribute]
        else:
            cls.__table_args__ = tuple(new_args)  # ty: ignore[unresolved-attribute]
    elif isinstance(existing, tuple):
        # User already has a tuple; merge positional args, merge dict if present.
        user_positional = [a for a in existing if not isinstance(a, dict)]
        user_dict: dict[str, Any] = next((a for a in existing if isinstance(a, dict)), {})
        merged_dict = {**user_dict, **schema_dict}
        merged_positional = user_positional + new_args
        if merged_dict:
            cls.__table_args__ = tuple(merged_positional) + (merged_dict,)  # ty: ignore[unresolved-attribute]
        else:
            cls.__table_args__ = tuple(merged_positional)  # ty: ignore[unresolved-attribute]
    elif isinstance(existing, dict):
        # User has only a dict (schema/extend_existing etc.); prepend new args.
        merged_dict = {**existing, **schema_dict}
        cls.__table_args__ = tuple(new_args) + (merged_dict,)  # ty: ignore[unresolved-attribute]


def apply_version_mapper_args(cls: type) -> None:
    """Wire SQLAlchemy's ``version_id_col`` to the ``_version`` column for versioned models.

    Must run AFTER ``prepare_fields`` (so ``cls.__dict__['_version']`` is the built
    mapped_column) and BEFORE ``super().__init_subclass__()`` (where SQLAlchemy reads
    ``__mapper_args__``). Merges with any user-supplied ``__mapper_args__``.
    """
    meta = getattr(cls, "__alchemiq_meta__", None)
    if not (meta and meta.versioned):
        return
    version_col = cls.__dict__.get("_version")
    if version_col is None:  # pragma: no cover - injection guarantees presence
        return
    inherited = dict(getattr(cls, "__mapper_args__", {}))
    cls.__mapper_args__ = {  # ty: ignore[unresolved-attribute]
        **inherited,
        "version_id_col": version_col,
    }


def prepare_fields(cls: type) -> dict[str, FieldType]:
    """Read *cls* own annotations, resolve each to a FieldType, wire mapped_column, return mapping.

    Uses cls.__annotations__ (not cls.__dict__["__annotations__"]) to support Python 3.14
    PEP 649 deferred annotations, which are no longer stored directly in __dict__.

    Also calls typing.get_type_hints() to handle PEP 563 string annotations
    (from __future__ import annotations in the user's module) before passing to resolve_field.

    Sets ``cls.__alchemiq_fields__`` as a side effect.
    """
    # Inject structural columns (deleted_at, created_at, updated_at) driven by MetaOptions
    # BEFORE get_type_hints so they land in evaluated and own_names.
    _inject_structural(cls)

    # Evaluate string annotations (PEP 563 / from __future__ import annotations).
    # This is needed when user modules use `from __future__ import annotations`.
    module = sys.modules.get(cls.__module__, None)
    globalns = getattr(module, "__dict__", {}) if module is not None else {}
    try:
        evaluated: dict[str, Any] = typing.get_type_hints(
            cls, globalns=globalns, localns={cls.__name__: cls}
        )
    except NameError:
        # Fall back to current own annotations for unresolvable forward refs.
        evaluated = dict(cls.__annotations__)

    own_names: list[str] = [
        name for name in cls.__annotations__ if not name.startswith("__") and name not in _RESERVED
    ]

    from alchemiq.model.relationships import (
        _REL_BUILDERS,
        ForeignKey,
        ManyToMany,
        detect_relationship,
    )

    fields: dict[str, FieldType] = {}
    for name in own_names:
        ann = evaluated.get(name, cls.__annotations__[name])
        value = cls.__dict__.get(name, _MISSING)

        native_py = _native_spec(ann, value)
        if native_py is NATIVE_RELATIONSHIP:
            continue  # native relationship: SQLAlchemy maps it; registered lazily post-configure
        if native_py is not None:
            # User-owned Mapped[...] column: register a passthrough field and let SQLAlchemy map
            # it verbatim - do NOT rewrite the annotation or call build_column/setattr.
            fields[name] = _NativeField(native_py)
            continue

        rel = detect_relationship(ann)
        if rel.kind:
            cfg = value if isinstance(value, (ForeignKey, ManyToMany)) else None
            fields.update(_REL_BUILDERS[rel.kind](cls, name, rel.target, rel, cfg, fields))
            continue

        field = resolve_field(name, ann, value)
        fields[name] = field
        # Rewrite annotation so SQLAlchemy declarative sees a Mapped[...] column.
        python_type: type = field.python_type
        cls.__annotations__[name] = Mapped[python_type]  # ty: ignore[invalid-type-form]
        setattr(cls, name, field.build_column())

    cls.__alchemiq_fields__ = fields  # ty: ignore[unresolved-attribute]
    return fields


def reconcile_native_fields(cls: type, fields: dict[str, FieldType]) -> None:
    """Fill each native field's config from its now-mapped Column (authoritative).

    Runs AFTER ``super().__init_subclass__()``: SQLAlchemy has reconciled ``nullable`` from the
    ``Mapped[...]`` annotation and built the real Column on ``cls.__table__``. Reading the public
    Table column (not ``MappedColumn`` internals) keeps this robust.
    """
    table = getattr(cls, "__table__", None)
    if table is None:  # pragma: no cover - concrete models always have __table__
        return
    for name, field in fields.items():
        if not isinstance(field, _NativeField):
            continue
        col = table.c.get(name)
        if col is None:  # pragma: no cover - native names always map to a column
            continue
        field.config = FieldConfig(
            primary_key=bool(col.primary_key),
            nullable=bool(col.nullable),
            unique=bool(col.unique),
            index=bool(col.index),
            server_default=col.server_default,
        )


def _native_rel_kind(direction: str, uselist: bool) -> str:
    if direction == "MANYTOMANY":
        return "many_to_many"
    if direction == "MANYTOONE":
        return "many_to_one"
    return "one_to_many" if uselist else "one_to_one"  # ONETOMANY


def register_native_relationships(model: type) -> None:
    """Register native (user-written) SQLAlchemy relationships into __alchemiq_relationships__.

    Idempotent (guarded by __alchemiq_native_rels_done__). SQLAlchemy resolves relationship
    targets/direction only at configure_mappers(); alchemiq-native sugar relationships are
    already registered eagerly and are skipped here.
    """
    if getattr(model, "__alchemiq_native_rels_done__", False):
        return
    rels = getattr(model, "__alchemiq_relationships__", None)
    if rels is None:
        return  # not a PG alchemiq Model (e.g. ClickHouseModel) - no relationship registry

    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy.orm import configure_mappers

    from alchemiq.model.relationships import RelationInfo

    configure_mappers()
    for r in sa_inspect(model).relationships:
        if r.key in rels:
            continue
        rels[r.key] = RelationInfo(
            r.key, r.mapper.class_, _native_rel_kind(r.direction.name, bool(r.uselist)), None
        )
    model.__alchemiq_native_rels_done__ = True  # ty: ignore[unresolved-attribute]


def register_validators(cls: type, fields: dict[str, FieldType]) -> None:
    """Wire set-event listeners onto each instrumented attribute for eager validation."""
    for name, field in fields.items():
        if isinstance(field, _NativeField):
            continue  # escape hatch: native columns get no eager validation
        attr = getattr(cls, name)

        def _listener(
            target: Any,
            value: Any,
            oldvalue: Any,
            initiator: Any,
            _f: FieldType = field,
            _n: str = name,
        ) -> Any:
            try:
                return _f.validate(value)
            except ValidationError as e:
                e.field = _n
                e.model = type(target).__name__
                raise

        event.listen(attr, "set", _listener, retval=True)


def install_descriptors(cls: type, fields: dict[str, FieldType]) -> None:
    """Install custom descriptors returned by field.descriptor(), if any."""
    for name, field in fields.items():
        desc = field.descriptor(name)
        if desc is not None:
            setattr(cls, name, desc)
