"""Serialization helpers: ``to_dict``, ``from_dict``, ``build_schema``, and ``to_pydantic``."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from decimal import Decimal
from enum import Enum as _Enum
from typing import Any, Literal
from uuid import UUID

from alchemiq.types.maybe import Nothing, Some
from alchemiq.types.strings import Password

SerMode = Literal["python", "json"]


def _pythonify(value: Any) -> Any:
    """Unwrap a Maybe container to its python value; pass everything else through.

    Python mode keeps native types (datetime, Decimal, Enum) as-is - it only
    strips the Some/Nothing wrapper that Maybe[T] columns hold on the attribute.
    """
    if value is Nothing:
        return None
    if isinstance(value, Some):
        return value.value
    return value


def _jsonify(value: Any) -> Any:
    if value is Nothing:
        return None
    if isinstance(value, Some):
        return _jsonify(value.value)
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    if isinstance(value, Decimal | UUID):
        return str(value)
    if isinstance(value, _Enum):
        return value.value
    return value


def _selected(name: str, include: set[str] | None, exclude: set[str] | None) -> bool:
    if include is not None and name not in include:
        return False
    return not (exclude is not None and name in exclude)


def to_dict(
    instance: Any,
    *,
    include: Iterable[str] | None = None,
    exclude: Iterable[str] | None = None,
    mode: SerMode = "python",
    relations: Iterable[str] = (),
) -> dict[str, Any]:
    """Serialize *instance* columns to a dict, applying include/exclude and mode conversion.

    ``Password`` fields are omitted unless explicitly listed in ``include``.
    ``Maybe[T]`` columns are unwrapped: ``Some(v)`` -> ``v``, ``Nothing`` -> ``None``.
    Pass relation names via ``relations`` to inline eagerly-loaded related objects.

    :param instance: the model instance to serialize.
    :param include: field name whitelist; ``None`` includes all (minus passwords).
    :param exclude: field names to omit; ``None`` omits nothing.
    :param mode: ``"python"`` keeps native types; ``"json"`` coerces to JSON-safe scalars.
    :param relations: names of loaded relationship attributes to inline recursively.
    :return: a ``dict`` keyed by field name.
    :raises RelationNotLoaded: if a name in *relations* is not loaded on *instance*.
    """
    inc = set(include) if include is not None else None
    exc = set(exclude) if exclude is not None else None
    fields: dict[str, Any] = type(instance).__alchemiq_fields__
    out: dict[str, Any] = {}
    for name, field in fields.items():
        explicitly_included = inc is not None and name in inc
        if isinstance(field, Password) and not explicitly_included:
            continue
        if not _selected(name, inc, exc):
            continue
        value = getattr(instance, name)
        out[name] = _jsonify(value) if mode == "json" else _pythonify(value)
    for rel_name in relations:
        related = getattr(instance, rel_name)  # may raise RelationNotLoaded
        if related is None:
            out[rel_name] = None
        elif isinstance(related, list):
            out[rel_name] = [to_dict(r, mode=mode) for r in related]
        else:
            out[rel_name] = to_dict(related, mode=mode)
    return out


def from_dict(cls: type, data: Mapping[str, Any]) -> Any:
    """Construct *cls* from *data*, raising ``ValidationError`` for unknown fields.

    :param cls: the model class to instantiate.
    :param data: mapping of field names to raw values.
    :return: a new instance of *cls*.
    :raises ValidationError: if *data* contains keys not in ``cls.__alchemiq_fields__``.
    """
    from alchemiq.exceptions import ValidationError

    fields: dict[str, Any] = cls.__alchemiq_fields__  # type: ignore
    unknown = set(data) - set(fields)
    if unknown:
        raise ValidationError(
            reason=f"unknown field(s): {', '.join(sorted(unknown))}", model=cls.__name__
        )
    return cls(**data)


def build_schema(
    cls: type,
    *,
    include: Iterable[str] | None = None,
    exclude: Iterable[str] | None = None,
) -> Any:
    """Build and cache a Pydantic model class for *cls* filtered by include/exclude.

    The result is memoised per ``(frozenset(include), frozenset(exclude))`` key on the
    model class.  ``Password`` fields are omitted unless explicitly whitelisted.

    :param cls: the model class whose columns define the schema fields.
    :param include: field name whitelist.
    :param exclude: field names to omit.
    :return: a ``pydantic.BaseModel`` subclass named ``<cls.__name__>Schema``.
    """
    from pydantic import create_model

    inc = frozenset(include) if include is not None else None
    exc = frozenset(exclude) if exclude is not None else None
    cache: dict[Any, Any] | None = cls.__dict__.get("__alchemiq_schema_cache__")
    if cache is None:
        cache = {}
        cls.__alchemiq_schema_cache__ = cache  # ty: ignore[unresolved-attribute]
    key = (inc, exc)
    cached = cache.get(key)
    if cached is not None:
        return cached

    inc_set = set(inc) if inc is not None else None
    exc_set = set(exc) if exc is not None else None
    fields: dict[str, Any] = cls.__alchemiq_fields__  # ty: ignore[unresolved-attribute]
    definitions: dict[str, Any] = {}
    for name, field in fields.items():
        explicitly_included = inc_set is not None and name in inc_set
        if isinstance(field, Password) and not explicitly_included:
            continue
        if not _selected(name, inc_set, exc_set):
            continue
        py: type = field.python_type
        if field.config.nullable:
            definitions[name] = (py | None, None)
        else:
            definitions[name] = (py, ...)
    schema = create_model(f"{cls.__name__}Schema", **definitions)
    cache[key] = schema
    return schema


def to_pydantic(instance: Any) -> Any:
    """Convert *instance* to a validated Pydantic schema object using ``build_schema``.

    :param instance: the model instance to convert.
    :return: a validated ``pydantic.BaseModel`` instance.
    """
    schema = build_schema(type(instance))
    return schema.model_validate(to_dict(instance, mode="python"))
