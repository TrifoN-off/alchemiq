"""Query ClickHouse system tables to introspect live schema state."""

from __future__ import annotations

from typing import Any


async def live_tables(client: Any, database: str) -> set[str]:
    """Return the names of all tables in *database* from ``system.tables``."""
    res = await client.query(
        "SELECT name FROM system.tables WHERE database = {database:String}",
        parameters={"database": database},
    )
    return {row[0] for row in res.result_rows}


async def live_columns(client: Any, database: str, table: str) -> dict[str, str]:
    """Return ``{column_name: type_string}`` for *table* from ``system.columns``."""
    res = await client.query(
        "SELECT name, type FROM system.columns "
        "WHERE database = {database:String} AND table = {table:String}",
        parameters={"database": database, "table": table},
    )
    return {row[0]: row[1] for row in res.result_rows}


async def live_engine(client: Any, database: str, table: str) -> str:
    """Return the engine name for *table*, or an empty string if the table is absent."""
    res = await client.query(
        "SELECT engine FROM system.tables "
        "WHERE database = {database:String} AND table = {table:String}",
        parameters={"database": database, "table": table},
    )
    return res.result_rows[0][0] if res.result_rows else ""
