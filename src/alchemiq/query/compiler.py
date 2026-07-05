"""Compile ``QuerySet`` and ``Q`` objects to SQLAlchemy ``Select`` statements."""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, not_, or_, select, true
from sqlalchemy.orm import aliased

from alchemiq.exceptions import QueryError, UnknownFieldError, UnknownOperatorError
from alchemiq.query.lookups import LOOKUPS, parse_key
from alchemiq.query.q import Q


class _JoinContext:
    """Accumulates ordered, deduplicated relationship joins for one Select.

    Self-referential joins (where target table == source table) are handled via
    SQLAlchemy ``aliased()`` so both sides resolve to different table instances.
    The alias is stored in ``_aliases`` and used by callers for column references.
    """

    def __init__(self, root_model: type) -> None:
        self.joins: list[tuple[Any, Any]] = []
        self._seen: set[tuple[type, str]] = set()
        self._joined_tables: set[str] = {root_model.__tablename__}  # ty: ignore[unresolved-attribute]
        self._aliases: dict[tuple[type, str], Any] = {}

    def add(self, source_model: type, relation_name: str) -> None:
        key = (source_model, relation_name)
        if key in self._seen:
            return
        rels: dict[str, Any] = getattr(source_model, "__alchemiq_relationships__", {})
        target: type = rels[relation_name].target  # ty: ignore[unresolved-attribute]
        target_table: str = target.__tablename__  # ty: ignore[unresolved-attribute]
        rel_attr = getattr(source_model, relation_name)
        if target_table in self._joined_tables:
            # Self-referential join: target == source table. Use aliased() to
            # create a distinct table alias so SQLAlchemy can distinguish sides.
            if target is not source_model:
                raise QueryError(
                    f"Query joins table {target_table!r} via more than one relationship; "
                    "multiple relationships to the same table need aliasing (not supported in v1)"
                )
            alias = aliased(target)
            self._aliases[key] = alias
            self.joins.append((rel_attr, alias))
        else:
            self._joined_tables.add(target_table)
            self.joins.append((rel_attr, None))
        self._seen.add(key)

    def resolve_target(self, source_model: type, relation_name: str) -> Any:
        """Return the alias (for self-ref joins) or the target class itself."""
        key = (source_model, relation_name)
        alias = self._aliases.get(key)
        if alias is not None:
            return alias
        rels: dict[str, Any] = getattr(source_model, "__alchemiq_relationships__", {})
        return rels[relation_name].target  # ty: ignore[unresolved-attribute]


def compile_q(q: Q, model: type, join_ctx: _JoinContext | None = None) -> Any:
    """Recursively compile a ``Q`` tree into a SQLAlchemy clause element.

    Relationship traversal segments accumulate JOIN entries in *join_ctx*;
    pass ``None`` to restrict compilation to own-column filters only.
    Raises ``QueryError`` if a traversal is
    encountered without a *join_ctx*.
    """
    clauses: list[Any] = []
    for child in q.children:
        if isinstance(child, Q):
            clauses.append(compile_q(child, model, join_ctx))
        else:
            key, value = child
            clauses.append(_compile_leaf(key, value, model, join_ctx))

    if not clauses:
        expr: Any = true()
    elif q.connector == Q.OR:
        expr = or_(*clauses)
    else:
        expr = and_(*clauses)

    if q.negated:
        expr = not_(expr)
    return expr


def _underlying_cls(obj: Any) -> type:
    """Return the mapped Python class for a model class or an aliased() instance."""
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy.orm.util import AliasedInsp

    if isinstance(obj, type):
        return obj
    insp = sa_inspect(obj, raiseerr=False)
    if isinstance(insp, AliasedInsp):
        return insp.mapper.class_
    return type(obj)


def _compile_leaf(key: str, value: Any, model: type, join_ctx: _JoinContext | None = None) -> Any:
    path, op = parse_key(key)
    current: Any = model
    did_self_ref = False
    for segment in path[:-1]:
        if did_self_ref:
            raise QueryError(
                "self-referential traversal deeper than one relationship hop is not supported"
            )
        current_cls: type = _underlying_cls(current)
        rels: dict[str, Any] = getattr(current_cls, "__alchemiq_relationships__", {})
        cols: dict[str, Any] = getattr(current_cls, "__alchemiq_fields__", {})
        if segment in rels:
            if join_ctx is None:
                raise QueryError("Relationship traversal requires a QuerySet (use .compile())")
            target_cls: type = rels[segment].target
            join_ctx.add(current_cls, segment)
            current = join_ctx.resolve_target(current_cls, segment)
            if target_cls is current_cls:
                did_self_ref = True
        elif segment in cols:
            raise UnknownOperatorError(f"Unknown operator in {key!r}")
        else:
            raise UnknownFieldError(
                f"{current_cls.__name__} has no field or relationship {segment!r}"
            )
    field = path[-1]
    current_cls = _underlying_cls(current)
    fields: dict[str, Any] = getattr(current_cls, "__alchemiq_fields__", {})
    if field not in fields:
        raise UnknownFieldError(f"{current_cls.__name__} has no field {field!r}")
    column = getattr(current, field)
    return LOOKUPS[op](column, value)


def _order_columns(model: type, order: tuple[str, ...]) -> list[Any]:
    cols: list[Any] = []
    for spec in order:
        if spec.startswith("-"):
            cols.append(getattr(model, spec[1:]).desc())
        else:
            cols.append(getattr(model, spec).asc())
    return cols


def compile_select(qs: Any) -> Any:
    """Compile a ``QuerySet`` to a fully-formed SQLAlchemy ``Select`` statement.

    Applies filters, joins, soft-delete predicate, projection, distinct,
    order, limit, and offset. Does not execute; no I/O is performed.
    """
    from sqlalchemy.orm import configure_mappers

    configure_mappers()
    model = qs.model
    from alchemiq.model.pipeline import register_native_relationships

    register_native_relationships(model)
    join_ctx = _JoinContext(model)
    where_clauses = [compile_q(q, model, join_ctx) for q in qs._where]

    if qs._projection:
        stmt = select(*(getattr(model, name) for name in qs._projection))
    else:
        stmt = select(model)

    for join_attr, join_alias in join_ctx.joins:
        if join_alias is not None:
            stmt = stmt.join(join_alias, join_attr)
        else:
            stmt = stmt.join(join_attr)
    from alchemiq.query.soft_delete import DeletedMode, deleted_predicate
    from alchemiq.runtime.soft_delete_filter import DELETED_MODE_OPTION

    deleted_mode: DeletedMode = getattr(qs, "_deleted", "exclude")
    predicate = deleted_predicate(model, deleted_mode)
    if predicate is not None:
        where_clauses.append(predicate)
    # Carry the mode to the session-level soft-delete listener so with_deleted()
    # / only_deleted() also lift the filter from relationship loads and joins.
    stmt = stmt.execution_options(**{DELETED_MODE_OPTION: deleted_mode})

    if where_clauses:
        stmt = stmt.where(and_(*where_clauses))
    if qs._distinct:
        stmt = stmt.distinct()
    if qs._order:
        stmt = stmt.order_by(*_order_columns(model, qs._order))
    if qs._limit is not None:
        stmt = stmt.limit(qs._limit)
    if qs._offset is not None:
        stmt = stmt.offset(qs._offset)
    return stmt
