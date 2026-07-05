"""Pydantic schema builders derived from alchemiq model field metadata."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, create_model

from alchemiq.exceptions import ConfigError
from alchemiq.model.serialization import build_schema
from alchemiq.query.soft_delete import is_soft_delete

_CACHE_ATTR = "__alchemiq_fastapi_schemas__"
_PAGE_ATTR = "__alchemiq_page_schema__"
_CURSOR_PAGE_ATTR = "__alchemiq_cursor_page_schema__"


def _fields(model: type) -> dict[str, Any]:
    return model.__alchemiq_fields__  # ty: ignore[unresolved-attribute]


def _cache(model: type) -> dict[str, Any]:
    cache: dict[str, Any] = model.__dict__.get(_CACHE_ATTR, {})
    if _CACHE_ATTR not in model.__dict__:
        setattr(model, _CACHE_ATTR, cache)
    return cache


def pk_name(model: type) -> str:
    """Return the primary-key field name for *model*.

    :param model: an alchemiq :class:`.Model` subclass.
    :return: the name of the field whose ``primary_key`` config is ``True``.
    :raises ConfigError: if no primary-key field is declared on *model*.
    """
    for name, field in _fields(model).items():
        if field.config.primary_key:
            return name
    raise ConfigError(f"{model.__name__} has no primary-key field")


def read_schema(model: type) -> type[BaseModel]:
    """Return the cached Pydantic read schema for *model* (all serialisable fields).

    The schema is derived from the model's field metadata and cached on the class.
    :func:`.crud_router` uses this automatically; call it directly to build a
    response schema for a custom endpoint.

    :param model: an alchemiq :class:`.Model` subclass.
    :return: a ``BaseModel`` subclass whose fields match the serialisable columns.
    """
    return build_schema(model)


def _writable(model: type) -> dict[str, Any]:
    """Own columns the client may set: exclude PK, server-managed, and soft-delete lifecycle fields.

    Omits the auto-injected ``deleted_at`` column on soft-delete models.
    """
    soft = is_soft_delete(model)
    out: dict[str, Any] = {}
    for name, field in _fields(model).items():
        if field.config.primary_key:
            continue
        if field.config.server_default is not None:  # CreatedAt / UpdatedAt
            continue
        if name == "deleted_at" and soft:
            continue
        out[name] = field
    return out


def create_schema(model: type) -> type[BaseModel]:
    """Return a cached Pydantic schema for creating *model* instances.

    Required fields are required; nullable fields are optional with a ``None`` default.
    PK, server-managed timestamps (``created_at``/``updated_at``), and ``deleted_at``
    (on soft-delete models) are excluded so clients cannot supply them.

    :param model: an alchemiq :class:`.Model` subclass.
    :return: a cached ``BaseModel`` subclass named ``{Model}Create``.
    """
    cache = _cache(model)
    if "create" in cache:
        return cache["create"]
    definitions: dict[str, Any] = {}
    for name, field in _writable(model).items():
        py = field.python_type
        definitions[name] = (py | None, None) if field.config.nullable else (py, ...)
    schema = create_model(f"{model.__name__}Create", **definitions)
    cache["create"] = schema
    return schema


def update_schema(model: type) -> type[BaseModel]:
    """Return a cached Pydantic schema for partial updates of *model* instances.

    All writable fields are optional with a ``None`` default.  :func:`.crud_router`
    passes the body through ``model_dump(exclude_unset=True)`` so only the fields
    the client actually supplied are applied.

    :param model: an alchemiq :class:`.Model` subclass.
    :return: a cached ``BaseModel`` subclass named ``{Model}Update``.
    """
    cache = _cache(model)
    if "update" in cache:
        return cache["update"]
    definitions: dict[str, Any] = {
        name: (field.python_type | None, None) for name, field in _writable(model).items()
    }
    schema = create_model(f"{model.__name__}Update", **definitions)
    cache["update"] = schema
    return schema


def cursor_page_schema(read_model: type[BaseModel]) -> type[BaseModel]:
    """Return a cached cursor-page envelope schema wrapping *read_model*.

    Produced automatically by :func:`.crud_router` when ``pagination="cursor"``.
    The envelope fields are ``items``, ``next_cursor``, ``prev_cursor``,
    ``has_next``, and ``has_prev``.

    :param read_model: a Pydantic ``BaseModel`` (typically from :func:`.read_schema`).
    :return: a cached ``BaseModel`` subclass named ``{ReadModel}CursorPage``.
    """
    cached = read_model.__dict__.get(_CURSOR_PAGE_ATTR)
    if cached is not None:
        return cached
    schema = create_model(
        f"{read_model.__name__}CursorPage",
        items=(list[read_model], ...),  # ty: ignore[invalid-type-form]
        next_cursor=(str | None, None),
        prev_cursor=(str | None, None),
        has_next=(bool, ...),
        has_prev=(bool, ...),
    )
    setattr(read_model, _CURSOR_PAGE_ATTR, schema)
    return schema


def page_schema(read_model: type[BaseModel]) -> type[BaseModel]:
    """Return a cached offset-page envelope schema wrapping *read_model*.

    Produced automatically by :func:`.crud_router` when ``pagination="offset"`` (default).
    The envelope fields are ``items``, ``total``, ``page``, ``size``, ``pages``,
    ``has_next``, and ``has_prev``.

    :param read_model: a Pydantic ``BaseModel`` (typically from :func:`.read_schema`).
    :return: a cached ``BaseModel`` subclass named ``{ReadModel}Page``.
    """
    cached = read_model.__dict__.get(_PAGE_ATTR)
    if cached is not None:
        return cached
    schema = create_model(
        f"{read_model.__name__}Page",
        items=(list[read_model], ...),  # ty: ignore[invalid-type-form]
        total=(int, ...),
        page=(int, ...),
        size=(int, ...),
        pages=(int, ...),
        has_next=(bool, ...),
        has_prev=(bool, ...),
    )
    setattr(read_model, _PAGE_ATTR, schema)
    return schema
