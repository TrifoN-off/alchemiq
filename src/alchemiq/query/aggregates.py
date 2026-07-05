"""Aggregate expression types for use with ``QuerySet.aggregate()``."""

from __future__ import annotations

from typing import Any

from sqlalchemy import distinct as sa_distinct
from sqlalchemy import func

from alchemiq.exceptions import QueryError


class Aggregate:
    """Base reduce-aggregate expression. ``resolve(model)`` builds a SQLAlchemy element."""

    func_name: str = ""

    def __init__(self, field: str) -> None:
        self.field = field

    def _column(self, model: type) -> Any:
        if "__" in self.field:
            raise QueryError(
                f"aggregate over traversal {self.field!r} is not supported (own columns only)"
            )
        fields: dict[str, Any] = getattr(model, "__alchemiq_fields__", {})
        if self.field not in fields:
            raise QueryError(f"{model.__name__} has no field {self.field!r}")
        return getattr(model, self.field)

    def resolve(self, model: type) -> Any:
        """Build the SQLAlchemy aggregate element for *model*."""
        return getattr(func, self.func_name)(self._column(model))


class Sum(Aggregate):
    """Sum of a numeric column."""

    func_name = "sum"


class Avg(Aggregate):
    """Arithmetic mean of a numeric column."""

    func_name = "avg"


class Min(Aggregate):
    """Minimum value of a column."""

    func_name = "min"


class Max(Aggregate):
    """Maximum value of a column."""

    func_name = "max"


class Count(Aggregate):
    """Row count, optionally over a specific column with ``distinct`` deduplication.

    ``Count()`` or ``Count("*")`` emits ``count(*)``;
    ``Count("field")`` emits ``count(field)``;
    ``Count("field", distinct=True)`` emits ``count(DISTINCT field)``.
    Raises ``QueryError`` for traversal fields (``__`` paths).

    E.g.::

        result = await QuerySet(Order).aggregate(
            n=Count(),
            unique_customers=Count("customer_id", distinct=True),
        )

    .. seealso:: :meth:`.QuerySet.aggregate` - pass aggregate expressions by alias.
    """

    def __init__(self, field: str = "*", *, distinct: bool = False) -> None:
        self.field = field
        self.distinct = distinct

    def resolve(self, model: type) -> Any:
        """Build the SQLAlchemy count element for *model*."""
        if self.field == "*":
            return func.count()
        column = self._column(model)
        return func.count(sa_distinct(column) if self.distinct else column)
