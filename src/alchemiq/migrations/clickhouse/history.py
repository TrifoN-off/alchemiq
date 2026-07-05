"""Manage the ``_alchemiq_migrations`` version-tracking table in ClickHouse."""

from __future__ import annotations

from typing import Any

HISTORY_TABLE = "_alchemiq_migrations"

_CREATE = (
    f"CREATE TABLE IF NOT EXISTS {HISTORY_TABLE} "
    "(revision String, name String, applied_at DateTime64(3) DEFAULT now64(3)) "
    "ENGINE = MergeTree ORDER BY revision"
)


async def ensure_history(client: Any) -> None:
    """Create the ``_alchemiq_migrations`` history table if it does not exist."""
    await client.command(_CREATE)


async def applied_revisions(client: Any) -> set[str]:
    """Return the set of revision identifiers recorded as applied."""
    result = await client.query(f"SELECT revision FROM {HISTORY_TABLE}")
    return {row[0] for row in result.result_rows}


async def record_applied(client: Any, revision: str, name: str) -> None:
    """Insert a row marking *revision* as applied, with migration class *name*."""
    await client.insert(HISTORY_TABLE, [[revision, name]], column_names=["revision", "name"])


async def remove_applied(client: Any, revision: str) -> None:
    """Delete the history row for *revision* (used by rollback)."""
    await client.command(
        f"DELETE FROM {HISTORY_TABLE} WHERE revision = {{revision:String}}",
        parameters={"revision": revision},
    )
