"""Render ClickHouse migration source files and DDL type strings."""

from __future__ import annotations

from typing import Any

from clickhouse_sqlalchemy.drivers.base import ClickHouseDialect  # ty: ignore[unresolved-import]

from alchemiq.migrations.clickhouse.operations import Operation, _repr_double_quotes

_DIALECT = ClickHouseDialect()

_HEADER = """from alchemiq.migrations import Migration


class {class_name}(Migration):
    revision = {revision}
    down_revision = {down_revision}

    def up(self, op):
{up_body}

    def down(self, op):
{down_body}
"""


def _repr_or_none(value: str | None) -> str:
    """Return double-quoted string repr, or bare 'None' for None."""
    return "None" if value is None else _repr_double_quotes(value)


def ch_type_string(column: Any) -> str:
    """Compile a SQLAlchemy column type to its ClickHouse DDL string."""
    return str(column.type.compile(dialect=_DIALECT))


def _body(ops: list[Operation], unsafe_stubs: list[str]) -> str:
    lines = [f"        {op.render_call()}" for op in ops]
    if unsafe_stubs:
        lines.append("        # --- MANUAL: unsafe operations, not generated automatically ---")
        lines.extend(f"        # {s}" for s in unsafe_stubs)
    if not lines:
        lines = ["        pass"]
    return "\n".join(lines)


def render_migration_source(
    *,
    revision: str,
    down_revision: str | None,
    class_name: str,
    up_ops: list[Operation],
    down_ops: list[Operation],
    unsafe_stubs: list[str],
) -> str:
    """Return the full Python source text for a new ClickHouse migration file.

    :param revision: zero-padded revision string (e.g. ``"0003"``).
    :param down_revision: previous revision, or ``None`` for the first migration.
    :param class_name: name of the generated ``Migration`` subclass.
    :param up_ops: safe operations to emit in ``up()``.
    :param down_ops: inverse operations to emit in ``down()``.
    :param unsafe_stubs: comment stubs for unsafe changes appended at the end of ``up()``.
    :return: the complete Python source string ready to write to a ``.py`` file.
    """
    return _HEADER.format(
        class_name=class_name,
        revision=_repr_or_none(revision),
        down_revision=_repr_or_none(down_revision),
        up_body=_body(up_ops, unsafe_stubs),
        down_body=_body(down_ops, []),
    )
