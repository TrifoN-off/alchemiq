"""SQLAlchemy eager-loading helpers (joinedload / selectinload) for relationships."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import joinedload, selectinload

from alchemiq.exceptions import QueryError


def _relation_attr(model: type, name: str) -> Any:
    if "__" in name:
        raise QueryError(f"Nested loading path {name!r} is not supported (single-level in v1)")
    rels: dict[str, Any] = getattr(model, "__alchemiq_relationships__", {})
    if name not in rels:
        raise QueryError(f"{model.__name__} has no relationship {name!r}")
    return getattr(model, name)


def apply_loaders(
    stmt: Any,
    model: type,
    select_related: tuple[str, ...],
    prefetch_related: tuple[str, ...],
) -> Any:
    """Attach ``joinedload`` / ``selectinload`` options to *stmt* for the named relationships.

    Each name must be a single-level relationship registered on *model*: a name containing
    ``"__"`` or one that is not a known relationship raises ``QueryError``.
    """
    from alchemiq.model.pipeline import register_native_relationships

    register_native_relationships(model)
    options: list[Any] = []
    for name in select_related:
        options.append(joinedload(_relation_attr(model, name)))
    for name in prefetch_related:
        options.append(selectinload(_relation_attr(model, name)))
    if options:
        stmt = stmt.options(*options)
    return stmt
