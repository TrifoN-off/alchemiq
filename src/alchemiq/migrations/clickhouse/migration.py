"""Base class for ClickHouse migration definitions."""

from __future__ import annotations

from alchemiq.migrations.clickhouse.operations import Operations


class Migration:
    """Base for a ClickHouse migration. Subclass and set revision/down_revision + up/down."""

    revision: str
    down_revision: str | None = None

    def up(self, op: Operations) -> None:
        """Record forward migration operations on *op*."""
        raise NotImplementedError

    def down(self, op: Operations) -> None:
        """Record rollback operations on *op*."""
        raise NotImplementedError
