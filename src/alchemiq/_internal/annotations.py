from __future__ import annotations

import types
from typing import Any, Union, get_args, get_origin

from alchemiq.exceptions import ConfigError
from alchemiq.types.base import _MISSING, Field, FieldType


def _split_optional(annotation: Any) -> tuple[Any, bool]:
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0], True
        raise ConfigError(f"Unsupported union annotation: {annotation!r}")
    return annotation, False


def resolve_field(name: str, annotation: Any, value: Any) -> FieldType:
    from alchemiq.types.maybe import Maybe, MaybeField

    if get_origin(annotation) is Maybe:
        (inner_ann,) = get_args(annotation)
        inner_field = resolve_field(name, inner_ann, _MISSING)
        return MaybeField(inner_field)

    inner, nullable = _split_optional(annotation)

    # Configured field instance in the value slot
    if isinstance(value, FieldType):
        field = value
        if field.python_type is object and isinstance(inner, type):
            field.python_type = inner
        _apply_nullable(field, nullable)
        return field

    # Parametrized field generic (PK[int], Array[int], ...) already a FieldType instance.
    if isinstance(inner, FieldType):
        _apply_nullable(inner, nullable)
        return inner

    # Semantic field-type class (Email, Money, ...).
    if isinstance(inner, type) and issubclass(inner, FieldType):
        field = inner()
        if value is not _MISSING:
            _set_default(field, value)
        _apply_nullable(field, nullable)
        return field

    # Plain python type (str/int/...) generic Field.
    if isinstance(inner, type):
        field = Field()
        field.python_type = inner
        if value is not _MISSING:
            _set_default(field, value)
        _apply_nullable(field, nullable)
        return field

    raise ConfigError(f"Cannot resolve field {name!r} from annotation {annotation!r}")


NATIVE_RELATIONSHIP: Any = object()


def _native_spec(annotation: Any, value: Any) -> Any:  # -> type | None | NATIVE_RELATIONSHIP
    """Classify a user-declared native SQLAlchemy attribute.

    ``None`` -> not native (fall through to detect_relationship / resolve_field).
    A ``type`` -> native COLUMN (config filled later by reconcile_native_fields).
    ``NATIVE_RELATIONSHIP`` -> native relationship: leave for SQLAlchemy, register lazily.
    """
    from sqlalchemy.orm import Mapped, Relationship

    from alchemiq.model.base import Model

    if isinstance(value, Relationship):  # `x = relationship(...)` with or without Mapped[]
        return NATIVE_RELATIONSHIP
    if get_origin(annotation) is not Mapped:
        return None
    (inner,) = get_args(annotation)
    py, _nullable = _split_optional(inner)
    if isinstance(py, type) and issubclass(py, Model):
        return NATIVE_RELATIONSHIP  # Mapped[User] - relationship by annotation
    if get_origin(py) in (list, set):
        (item,) = get_args(py)
        if isinstance(item, type) and issubclass(item, Model):
            return NATIVE_RELATIONSHIP  # Mapped[list[Tag]] - M2M by annotation
        return get_origin(py)  # Mapped[list[int]] - native ARRAY column
    return py  # Mapped[dict] / Mapped[int] / ... - native column


def _apply_nullable(field: FieldType, nullable: bool) -> None:
    if nullable and not field.config.nullable:
        object.__setattr__(field, "config", _with(field.config, nullable=True))


def _set_default(field: FieldType, default: Any) -> None:
    object.__setattr__(field, "config", _with(field.config, default=default))


def _with(config: Any, **changes: Any) -> Any:
    import dataclasses

    return dataclasses.replace(config, **changes)
