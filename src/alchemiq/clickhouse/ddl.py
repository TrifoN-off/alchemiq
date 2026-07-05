"""DDL helpers: create/drop CH tables and run OPTIMIZE on a model's table."""

from __future__ import annotations

from typing import Any

from clickhouse_sqlalchemy.drivers.base import ClickHouseDialect  # ty: ignore[unresolved-import]
from sqlalchemy.schema import CreateColumn

from alchemiq.clickhouse.connection import get_clickhouse_client
from alchemiq.clickhouse.model import ch_engine_of
from alchemiq.clickhouse.registry import ch_metadata

_DIALECT = ClickHouseDialect()


def _column_defs(model: type) -> str:
    table = model.__table__  # ty: ignore[unresolved-attribute]
    rendered = [str(CreateColumn(c).compile(dialect=_DIALECT)) for c in table.columns]
    return ",\n  ".join(rendered)


def create_table_sql(model: type) -> str:
    """Return the CREATE TABLE IF NOT EXISTS DDL string for *model*."""
    table = model.__table__  # ty: ignore[unresolved-attribute]
    engine = ch_engine_of(model)
    return (
        f"CREATE TABLE IF NOT EXISTS {table.name} (\n  "
        f"{_column_defs(model)}\n) {engine.engine_clause()}"
    )


async def create_clickhouse_tables() -> None:
    """Create all registered CH tables using ``CREATE TABLE IF NOT EXISTS``.

    Tables are created in ``ch_metadata`` dependency order.  Safe to call on every
    startup - existing tables are left unchanged.

    .. seealso:: :func:`.drop_clickhouse_tables` - tear down all CH tables.
    """
    client = await get_clickhouse_client()
    for table in ch_metadata.sorted_tables:
        model = _model_for(table)
        await client.command(create_table_sql(model))


async def drop_clickhouse_tables() -> None:
    """Drop all registered CH tables using ``DROP TABLE IF EXISTS``.

    Tables are dropped in reverse ``ch_metadata`` dependency order.

    .. seealso:: :func:`.create_clickhouse_tables` - recreate the tables.
    """
    client = await get_clickhouse_client()
    for table in reversed(ch_metadata.sorted_tables):
        await client.command(f"DROP TABLE IF EXISTS {table.name}")


async def optimize(model: type, *, cleanup: bool = False) -> None:
    """Run ``OPTIMIZE TABLE FINAL [CLEANUP]`` on *model*'s table.

    :param model: A :class:`.ClickHouseModel` subclass whose table to optimize.
    :param cleanup: If ``True``, appends ``CLEANUP`` to instruct
        ``ReplacingMergeTree`` to physically remove rows where ``is_deleted=1``
        once merged.  Requires ``allow_experimental_replacing_merge_with_cleanup``
        enabled on the CH server.

    .. seealso:: :meth:`.ClickHouseRepository.cleanup` - higher-level soft-delete cleanup.
    """
    client = await get_clickhouse_client()
    table = model.__table__  # ty: ignore[unresolved-attribute]
    sql = f"OPTIMIZE TABLE {table.name} FINAL" + (" CLEANUP" if cleanup else "")
    await client.command(sql)


def _model_for(table: Any) -> type:
    for mapper in _ch_metadata_mappers():
        if mapper.local_table is table:
            return mapper.class_
    raise LookupError(f"No CH model mapped to table {table.name!r}")


def _ch_metadata_mappers() -> Any:
    from alchemiq.clickhouse.registry import ch_mapper_registry

    return list(ch_mapper_registry.mappers)
