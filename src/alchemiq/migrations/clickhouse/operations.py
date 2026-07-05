"""ClickHouse DDL operation value-objects and the ``Operations`` recorder."""

from __future__ import annotations

from dataclasses import dataclass


def _repr_double_quotes(value: str) -> str:
    """Return repr of a string using double quotes."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


@dataclass(frozen=True)
class Column:
    """Descriptor for a ClickHouse table column.

    :ivar name: column name.
    :ivar type: ClickHouse type string (e.g. ``"UInt32"``).
    :ivar default: optional DEFAULT expression.
    :ivar codec: optional CODEC expression.
    """

    name: str
    type: str
    default: str | None = None
    codec: str | None = None

    def render(self) -> str:
        """Return the inline DDL fragment: ``name type [DEFAULT ...] [CODEC(...)]``."""
        out = f"{self.name} {self.type}"
        if self.default is not None:
            out += f" DEFAULT {self.default}"
        if self.codec is not None:
            out += f" CODEC({self.codec})"
        return out

    def render_call(self) -> str:
        """Return the Python source fragment that constructs this column via ``op.Column(...)``."""
        extra = ""
        if self.default is not None:
            extra += f", default={_repr_double_quotes(self.default)}"
        if self.codec is not None:
            extra += f", codec={_repr_double_quotes(self.codec)}"
        name_repr = _repr_double_quotes(self.name)
        type_repr = _repr_double_quotes(self.type)
        return f"op.Column({name_repr}, {type_repr}{extra})"


@dataclass(frozen=True)
class Operation:
    """Abstract base for a single ClickHouse DDL operation."""

    def to_sql(self) -> str:
        """Return the DDL SQL string for this operation."""
        raise NotImplementedError

    def render_call(self) -> str:
        """Return the Python source fragment that reconstructs this operation via ``op.*``."""
        raise NotImplementedError


@dataclass(frozen=True)
class CreateTable(Operation):
    """``CREATE TABLE IF NOT EXISTS`` with an explicit engine clause."""

    name: str
    columns: tuple[Column, ...]
    engine: str

    def to_sql(self) -> str:
        """Return the ``CREATE TABLE IF NOT EXISTS`` DDL string."""
        cols = ",\n  ".join(c.render() for c in self.columns)
        return f"CREATE TABLE IF NOT EXISTS {self.name} (\n  {cols}\n) {self.engine}"

    def render_call(self) -> str:
        """Return the ``op.create_table(...)`` source fragment."""
        cols = ", ".join(c.render_call() for c in self.columns)
        name_repr = _repr_double_quotes(self.name)
        engine_repr = _repr_double_quotes(self.engine)
        return f"op.create_table({name_repr}, [{cols}], {engine_repr})"


@dataclass(frozen=True)
class AddColumn(Operation):
    """``ALTER TABLE ... ADD COLUMN IF NOT EXISTS``."""

    table: str
    column: Column

    def to_sql(self) -> str:
        """Return the ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS`` DDL string."""
        return f"ALTER TABLE {self.table} ADD COLUMN IF NOT EXISTS {self.column.render()}"

    def render_call(self) -> str:
        """Return the ``op.add_column(...)`` source fragment."""
        return f"op.add_column({_repr_double_quotes(self.table)}, {self.column.render_call()})"


@dataclass(frozen=True)
class DropColumn(Operation):
    """``ALTER TABLE ... DROP COLUMN IF EXISTS``."""

    table: str
    name: str

    def to_sql(self) -> str:
        """Return the ``ALTER TABLE ... DROP COLUMN IF EXISTS`` DDL string."""
        return f"ALTER TABLE {self.table} DROP COLUMN IF EXISTS {self.name}"

    def render_call(self) -> str:
        """Return the ``op.drop_column(...)`` source fragment."""
        table_repr = _repr_double_quotes(self.table)
        name_repr = _repr_double_quotes(self.name)
        return f"op.drop_column({table_repr}, {name_repr})"


@dataclass(frozen=True)
class DropTable(Operation):
    """``DROP TABLE IF EXISTS``."""

    name: str

    def to_sql(self) -> str:
        """Return the ``DROP TABLE IF EXISTS`` DDL string."""
        return f"DROP TABLE IF EXISTS {self.name}"

    def render_call(self) -> str:
        """Return the ``op.drop_table(...)`` source fragment."""
        return f"op.drop_table({_repr_double_quotes(self.name)})"


@dataclass(frozen=True)
class RawSQL(Operation):
    """Arbitrary SQL statement passed through verbatim."""

    sql: str

    def to_sql(self) -> str:
        """Return the raw SQL string unchanged."""
        return self.sql

    def render_call(self) -> str:
        """Return the ``op.execute(...)`` source fragment."""
        return f"op.execute({_repr_double_quotes(self.sql)})"


# Alias used inside Operations to avoid shadowing by the staticmethod of the same name.
_Column = Column


class Operations:
    """Recorder passed to Migration.up/down - appends operations, runs nothing."""

    def __init__(self) -> None:
        self.operations: list[Operation] = []

    @staticmethod
    def Column(
        name: str,
        type: str,
        *,
        default: str | None = None,
        codec: str | None = None,
    ) -> _Column:
        """Construct a ``Column`` descriptor for use in migration methods."""
        return _Column(name, type, default=default, codec=codec)

    def create_table(
        self,
        name: str,
        columns: list[_Column],
        engine: str,
    ) -> None:
        """Enqueue a ``CREATE TABLE IF NOT EXISTS`` operation."""
        self.operations.append(CreateTable(name, tuple(columns), engine))

    def add_column(
        self,
        table: str,
        column: _Column,
    ) -> None:
        """Enqueue an ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS`` operation."""
        self.operations.append(AddColumn(table, column))

    def drop_column(self, table: str, name: str) -> None:
        """Enqueue an ``ALTER TABLE ... DROP COLUMN IF EXISTS`` operation."""
        self.operations.append(DropColumn(table, name))

    def drop_table(self, name: str) -> None:
        """Enqueue a ``DROP TABLE IF EXISTS`` operation."""
        self.operations.append(DropTable(name))

    def execute(self, sql: str) -> None:
        """Enqueue a raw SQL statement to be executed verbatim."""
        self.operations.append(RawSQL(sql))
