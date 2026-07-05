"""Relationship detection and builder functions for FK, M2M, and 1:1 annotations."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, get_args, get_origin

from sqlalchemy import ForeignKey as SAForeignKey
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from alchemiq._internal.annotations import _split_optional
from alchemiq.exceptions import ConfigError
from alchemiq.types.base import Field, FieldType

if TYPE_CHECKING:
    type OneToOne[T] = T  # static: `profile: OneToOne[Profile]` resolves to Profile
else:

    class OneToOne[T]:
        """Marker for a one-to-one relationship: ``profile: OneToOne[Profile]``.

        Wires a unique, non-nullable FK column ``<name>_id`` on the declaring model
        and a scalar back-reference ``<snake_cls>`` on the target.

        E.g.::

            class Profile(Model):
                id: PK[int]
                bio: str

            class User(Model):
                id: PK[int]
                profile: OneToOne[Profile]

        The ``user.profile_id`` FK column is added automatically;
        ``profile.user`` is the reverse scalar accessor (``_snake(cls.__name__)``).

        .. note::

            Under ``TYPE_CHECKING`` ``OneToOne[T]`` is an alias for ``T``, so
            static analysers infer the correct type without seeing the runtime class.

        .. seealso:: :class:`.ForeignKey` - many-to-one (nullable or required).
        """


_CAMEL_SPLIT_1 = re.compile(r"([a-zA-Z])([A-Z][a-z]+)")
_CAMEL_SPLIT_2 = re.compile(r"([a-z])([A-Z])")


def _snake(name: str) -> str:
    """Convert CamelCase (incl. acronyms like M2M) to snake_case.

    Two-pass approach: first split on a letter before a cap+lower sequence
    (handles HTTPServer -> HTTP_Server), then split on lower-before-upper
    (handles SomeClass -> Some_Class). Digits are kept with the preceding caps
    group so M2MPost -> m2m_post.
    """
    name = _CAMEL_SPLIT_1.sub(r"\1_\2", name)
    name = _CAMEL_SPLIT_2.sub(r"\1_\2", name)
    return name.lower()


@dataclass(frozen=True)
class ForeignKey:
    """Optional override marker for a many-to-one FK inferred from the annotation.

    When the annotation alone is enough (most cases) you can omit the marker.
    Use ``ForeignKey(...)`` only to customise ``on_delete`` behaviour or to
    resolve a ``related_name`` collision.

    E.g.::

        class Member(Model):
            id: PK[int]
            org: Org                             # required -> ON DELETE RESTRICT (default)
            sponsor: Org | None = ForeignKey(related_name="sponsored")  # optional + custom name
            owner: Org = ForeignKey(on_delete="CASCADE", related_name="docs")

    :param on_delete: PostgreSQL ``ON DELETE`` action (``"RESTRICT"``, ``"CASCADE"``,
        ``"SET NULL"``).  Inferred from nullability when omitted.
    :param related_name: name of the reverse accessor on the target model.
        Defaults to ``<snake_cls>_set``.

    .. seealso:: :class:`.OneToOne` - unique FK with a scalar reverse accessor.
    """

    on_delete: str | None = None
    related_name: str | None = None


@dataclass(frozen=True)
class ManyToMany:
    """Optional override marker for a ``list[Model]`` many-to-many annotation.

    Without the marker the join-table name is derived automatically as
    ``sorted(a_table, b_table)`` joined with ``_``.  Use ``ManyToMany(...)``
    to supply a custom ``related_name`` or ``secondary`` table name.

    E.g.::

        class Tag(Model):
            id: PK[int]
            name: str

        class Post(Model):
            id: PK[int]
            tags: list[Tag]                         # auto join-table
            featured: list[Tag] = ManyToMany(       # explicit names
                related_name="featured_post_set",
                secondary="post_featured_tag",
            )

    :param related_name: name of the reverse accessor on the target model.
        Defaults to ``<snake_cls>_set``.
    :param secondary: explicit name for the auto-created association table.
        Required when declaring M2M from both sides to avoid a collision.

    .. seealso:: :class:`.ForeignKey` - many-to-one relationship.
    """

    related_name: str | None = None
    secondary: str | None = None


@dataclass(frozen=True)
class DetectedRelation:
    """Result of ``detect_relationship``: the relationship kind and its target model."""

    kind: str  # "" | "many_to_one" | "many_to_many" | "one_to_one"
    target: type | None
    nullable: bool


@dataclass(frozen=True)
class RelationInfo:
    """Runtime record of a registered relationship stored in ``__alchemiq_relationships__``."""

    name: str
    target: type
    direction: str  # "many_to_one" | "one_to_many" | "many_to_many" | "one_to_one"
    fk_attr: str | None


def detect_relationship(annotation: Any) -> DetectedRelation:
    """Classify an annotation as a relationship. Strips Maybe[...] / | None for the scalar case."""
    from alchemiq.model.base import Model
    from alchemiq.types.maybe import Maybe

    if get_origin(annotation) is OneToOne:
        (target,) = get_args(annotation)
        return DetectedRelation("one_to_one", target, False)

    if get_origin(annotation) in (list, set):
        args = get_args(annotation)
        if len(args) == 1 and isinstance(args[0], type) and issubclass(args[0], Model):
            return DetectedRelation("many_to_many", args[0], False)
        return DetectedRelation("", None, False)

    nullable = False
    if get_origin(annotation) is Maybe:
        (annotation,) = get_args(annotation)
        nullable = True
    else:
        annotation, nullable = _split_optional(annotation)
    if isinstance(annotation, type) and issubclass(annotation, Model):
        return DetectedRelation("many_to_one", annotation, nullable)
    return DetectedRelation("", None, nullable)


def _target_pk(target: type, local_fields: dict[str, Any] | None = None) -> tuple[str, Any, type]:
    fields = local_fields if local_fields is not None else target.__alchemiq_fields__  # ty: ignore[unresolved-attribute]
    for fname, field in fields.items():
        if field.config.primary_key:
            return fname, field.column_type(), field.python_type
    raise ConfigError(f"{target.__name__} has no primary key to reference")


def build_relationship(
    cls: type,
    name: str,
    target: type,
    nullable: bool,
    fk_cfg: ForeignKey | None,
    fields: dict[str, Any] | None = None,
) -> FieldType:
    """Wire a many-to-one FK column + relationship onto ``cls`` and return a synthetic FK field."""
    on_delete = (
        fk_cfg.on_delete
        if (fk_cfg and fk_cfg.on_delete)
        else ("SET NULL" if nullable else "RESTRICT")
    )
    related_name = (
        fk_cfg.related_name if (fk_cfg and fk_cfg.related_name) else f"{_snake(cls.__name__)}_set"
    )
    if related_name in target.__alchemiq_relationships__:  # ty: ignore[unresolved-attribute]
        raise ConfigError(
            f"related_name {related_name!r} collides on {target.__name__}; "
            f"set a distinct related_name for {cls.__name__}.{name}"
        )

    # For a self-referential FK, target.__alchemiq_fields__ isn't set yet (mid-build),
    # so pass the in-progress fields dict instead.
    pk_name, pk_type, pk_python = _target_pk(target, fields if target is cls else None)
    fk_attr = f"{name}_id"

    cls.__annotations__[fk_attr] = Mapped[pk_python]  # ty: ignore[invalid-type-form]
    setattr(
        cls,
        fk_attr,
        mapped_column(
            pk_type,
            SAForeignKey(f"{target.__tablename__}.{pk_name}", ondelete=on_delete),  # ty: ignore[unresolved-attribute]
            nullable=nullable,
        ),
    )

    rel_ann = Mapped[target | None] if nullable else Mapped[target]  # ty: ignore[invalid-type-form]
    cls.__annotations__[name] = rel_ann  # ty: ignore[invalid-type-form]
    rel_kwargs: dict[str, Any] = {
        "foreign_keys": f"{cls.__name__}.{fk_attr}",
        "backref": backref(related_name, lazy="raise_on_sql"),
        "lazy": "raise_on_sql",
    }
    if target is cls:
        rel_kwargs["remote_side"] = f"{cls.__name__}.{pk_name}"
    setattr(cls, name, relationship(target.__name__, **rel_kwargs))

    cls.__alchemiq_relationships__[name] = RelationInfo(name, target, "many_to_one", fk_attr)  # ty: ignore[unresolved-attribute]
    target.__alchemiq_relationships__[related_name] = RelationInfo(  # ty: ignore[unresolved-attribute]
        related_name, cls, "one_to_many", fk_attr
    )

    # Synthetic Field for querying/serialization.
    fk_field = Field(nullable=nullable)
    fk_field.python_type = pk_python
    return fk_field


def build_many_to_one(
    cls: type, name: str, target: type, rel: DetectedRelation, cfg: Any, fields: dict[str, Any]
) -> dict[str, FieldType]:
    """Build a many-to-one relationship; returns a ``{<name>_id: Field}`` synthetic field dict."""
    fk_cfg = cfg if isinstance(cfg, ForeignKey) else None
    fk_field = build_relationship(cls, name, target, rel.nullable, fk_cfg, fields)
    return {f"{name}_id": fk_field}


def _build_assoc_table(name: str, cls: type, target: type, fields: dict[str, Any]) -> Any:
    from sqlalchemy import Column, Table

    from alchemiq.model.registry import metadata

    if name in metadata.tables:
        raise ConfigError(
            f"M2M association table {name!r} already exists; declare the M2M on one side only, "
            f"or pass ManyToMany(secondary=...) for a distinct table"
        )
    a_pk, a_type, _ = _target_pk(cls, fields)
    b_pk, b_type, _ = _target_pk(target)
    a_col, b_col = f"{_snake(cls.__name__)}_id", f"{_snake(target.__name__)}_id"
    a_fk = SAForeignKey(f"{cls.__tablename__}.{a_pk}", ondelete="CASCADE")  # ty: ignore[unresolved-attribute]
    b_fk = SAForeignKey(f"{target.__tablename__}.{b_pk}", ondelete="CASCADE")  # ty: ignore[unresolved-attribute]
    return Table(
        name,
        metadata,
        Column(a_col, a_type, a_fk, primary_key=True),
        Column(b_col, b_type, b_fk, primary_key=True),
    )


def build_many_to_many(
    cls: type, name: str, target: type, rel: DetectedRelation, cfg: Any, fields: dict[str, Any]
) -> dict[str, FieldType]:
    """Build a M2M relationship with an auto-created join table; returns an empty field dict."""
    if target is cls:
        raise ConfigError(
            f"self-referential M2M ({cls.__name__}.{name}) is not supported by the list[Model] "
            f"sugar in v1; use a native relationship(secondary=...)"
        )
    m2m = cfg if isinstance(cfg, ManyToMany) else None
    related_name = m2m.related_name if m2m and m2m.related_name else f"{_snake(cls.__name__)}_set"
    if related_name in target.__alchemiq_relationships__:  # ty: ignore[unresolved-attribute]
        raise ConfigError(
            f"related_name {related_name!r} collides on {target.__name__}; "
            f"set ManyToMany(related_name=...) for {cls.__name__}.{name}"
        )
    assoc_name = (
        m2m.secondary
        if m2m and m2m.secondary
        else "_".join(sorted((cls.__tablename__, target.__tablename__)))  # ty: ignore[unresolved-attribute]
    )
    assoc = _build_assoc_table(assoc_name, cls, target, fields)
    cls.__annotations__[name] = Mapped[list[target]]  # ty: ignore[invalid-type-form]
    setattr(
        cls,
        name,
        relationship(
            target.__name__,
            secondary=assoc,
            lazy="raise_on_sql",
            backref=backref(related_name, lazy="raise_on_sql"),
        ),
    )
    cls.__alchemiq_relationships__[name] = RelationInfo(name, target, "many_to_many", None)  # ty: ignore[unresolved-attribute]
    target.__alchemiq_relationships__[related_name] = RelationInfo(  # ty: ignore[unresolved-attribute]
        related_name, cls, "many_to_many", None
    )
    return {}


def build_one_to_one(
    cls: type, name: str, target: type, rel: DetectedRelation, cfg: Any, fields: dict[str, Any]
) -> dict[str, FieldType]:
    """Build a one-to-one relationship with a unique FK column; returns the FK synthetic field."""
    related_name = _snake(cls.__name__)  # scalar reverse, singular (not <class>_set)
    if related_name in target.__alchemiq_relationships__:  # ty: ignore[unresolved-attribute]
        raise ConfigError(
            f"reverse accessor {related_name!r} collides on {target.__name__} "
            f"for {cls.__name__}.{name}"
        )
    pk_name, pk_type, pk_python = _target_pk(target, fields if target is cls else None)
    fk_attr = f"{name}_id"
    cls.__annotations__[fk_attr] = Mapped[pk_python]  # ty: ignore[invalid-type-form]
    setattr(
        cls,
        fk_attr,
        mapped_column(
            pk_type,
            SAForeignKey(f"{target.__tablename__}.{pk_name}", ondelete="RESTRICT"),  # ty: ignore[unresolved-attribute]
            unique=True,
            nullable=False,
        ),
    )
    cls.__annotations__[name] = Mapped[target]  # ty: ignore[invalid-type-form]
    setattr(
        cls,
        name,
        relationship(
            target.__name__,
            foreign_keys=f"{cls.__name__}.{fk_attr}",
            backref=backref(related_name, uselist=False, lazy="raise_on_sql"),
            lazy="raise_on_sql",
        ),
    )
    cls.__alchemiq_relationships__[name] = RelationInfo(name, target, "one_to_one", fk_attr)  # ty: ignore[unresolved-attribute]
    target.__alchemiq_relationships__[related_name] = RelationInfo(  # ty: ignore[unresolved-attribute]
        related_name, cls, "one_to_one", fk_attr
    )
    fk_field = Field(nullable=False)
    fk_field.python_type = pk_python
    return {fk_attr: fk_field}


_REL_BUILDERS: dict[str, Callable[..., dict[str, FieldType]]] = {
    "many_to_one": build_many_to_one,
    "many_to_many": build_many_to_many,
    "one_to_one": build_one_to_one,
}
