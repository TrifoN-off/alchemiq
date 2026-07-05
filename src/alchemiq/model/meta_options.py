"""MetaOptions dataclass and ``parse_meta`` - parse a model's inner ``class Meta``."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class Index:
    """A database index on one or more columns, declared inside ``class Meta``.

    E.g.::

        class Article(Model):
            id: PK[int]
            slug: str
            author_id: int

            class Meta:
                indexes = [Index("slug", unique=True), Index("author_id")]

    :param columns: one or more column names to index.
    :param unique: when ``True``, emits a ``UNIQUE INDEX``; defaults to ``False``.
    """

    columns: tuple[str, ...]
    unique: bool = False

    def __init__(self, *columns: str, unique: bool = False) -> None:
        object.__setattr__(self, "columns", columns)
        object.__setattr__(self, "unique", unique)


@dataclass(frozen=True)
class Unique:
    """Shorthand for a unique constraint on one or more columns.

    Equivalent to ``Index(*columns, unique=True)`` but expressed as a
    table-level ``UNIQUE`` constraint rather than an index.

    E.g.::

        class Meta:
            constraints = [Unique("email"), Unique("slug", "tenant_id")]

    :param columns: one or more column names that must be unique together.
    """

    columns: tuple[str, ...]

    def __init__(self, *columns: str) -> None:
        object.__setattr__(self, "columns", columns)


@dataclass(frozen=True)
class Check:
    """A ``CHECK`` constraint with a raw SQL expression.

    E.g.::

        class Meta:
            constraints = [Check("price > 0"), Check("end_date > start_date")]

    :param expression: a raw SQL boolean expression passed verbatim to the DDL.
    """

    expression: str


@dataclass(frozen=True)
class MetaOptions:
    """Parsed, frozen representation of a model's inner ``class Meta``.

    Populated by ``parse_meta`` during ``__init_subclass__``; consumed by
    the pipeline to inject structural columns and configure SQLAlchemy mapper args.
    """

    soft_delete: bool = False
    timestamps: bool = False
    outbox: bool = False
    versioned: bool = False
    table_name: str | None = None
    schema: str | None = None
    abstract: bool = False
    indexes: tuple[Index, ...] = field(default_factory=tuple)
    constraints: tuple[Any, ...] = field(default_factory=tuple)


_KNOWN: frozenset[str] = frozenset(
    {
        "soft_delete",
        "timestamps",
        "outbox",
        "versioned",
        "table_name",
        "schema",
        "abstract",
        "indexes",
        "constraints",
    }
)


def parse_meta(cls: type) -> MetaOptions:
    """Return a ``MetaOptions`` for *cls*, merging inherited options with own ``Meta``.

    Subclass values always win over inherited ones.

    :param cls: the model class being defined.
    :return: a frozen ``MetaOptions`` with all flags resolved.
    """
    base: MetaOptions = getattr(cls, "__alchemiq_meta__", MetaOptions())
    inner = cls.__dict__.get("Meta")
    if inner is None:
        return base
    changes: dict[str, Any] = {}
    for key in _KNOWN:
        if hasattr(inner, key):
            val = getattr(inner, key)
            if key in ("indexes", "constraints"):
                val = tuple(val)
            changes[key] = val
    return replace(base, **changes)
