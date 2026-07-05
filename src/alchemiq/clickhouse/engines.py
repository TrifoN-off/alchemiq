"""ClickHouse MergeTree-family engine descriptors used in ClickHouseModel.Meta.engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _cols(value: str | tuple[str, ...] | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return "(" + ", ".join(value) + ")"


@dataclass(frozen=True)
class _Engine:
    order_by: str | tuple[str, ...]
    partition_by: str | tuple[str, ...] | None = None
    primary_key: str | tuple[str, ...] | None = None
    ttl: str | None = None
    sample_by: str | None = None
    settings: dict[str, Any] | None = None

    _name: str = field(default="MergeTree", init=False)

    def _engine_head(self) -> str:
        return self._name

    def engine_clause(self) -> str:
        parts = [f"ENGINE = {self._engine_head()}", f"ORDER BY {_cols(self.order_by)}"]
        if self.partition_by is not None:
            parts.append(f"PARTITION BY {_cols(self.partition_by)}")
        if self.primary_key is not None:
            parts.append(f"PRIMARY KEY {_cols(self.primary_key)}")
        if self.sample_by is not None:
            parts.append(f"SAMPLE BY {self.sample_by}")
        if self.ttl is not None:
            parts.append(f"TTL {self.ttl}")
        if self.settings:
            kv = ", ".join(f"{k} = {v}" for k, v in self.settings.items())
            parts.append(f"SETTINGS {kv}")
        return " ".join(parts)


@dataclass(frozen=True)
class MergeTree(_Engine):
    """Standard MergeTree engine - general-purpose append-only analytics table.

    E.g.::

        from alchemiq.clickhouse.engines import MergeTree

        engine = MergeTree(
            order_by=("event_time", "user_id"),
            partition_by="toYYYYMM(event_time)",
            ttl="event_time + INTERVAL 90 DAY",
        )

    .. seealso:: :class:`.ReplacingMergeTree` - for deduplication or soft-delete.
    """

    _name: str = field(default="MergeTree", init=False)


@dataclass(frozen=True)
class ReplacingMergeTree(_Engine):
    """ReplacingMergeTree engine - deduplicates rows by ORDER BY key on merge.

    Required for soft-delete models (``Meta.soft_delete=True``).  When ``version``
    and ``is_deleted`` are set (as :class:`.ClickHouseModel` does automatically for
    soft-delete models), ``SELECT ... FINAL`` retains the row with the highest
    ``version`` value and filters out rows where ``is_deleted=1``.

    E.g.::

        from alchemiq.clickhouse.engines import ReplacingMergeTree

        # basic dedup by version column:
        engine = ReplacingMergeTree(order_by="key", version="ver")

        # with soft-delete support (set automatically by Meta.soft_delete=True):
        engine = ReplacingMergeTree(
            order_by=("key",),
            version="_version",
            is_deleted="is_deleted",
        )

    :param version: Column name used as the deduplication version (latest value wins).
    :param is_deleted: Column name that marks tombstone rows (``1`` = deleted).
        When set, ``SELECT ... FINAL`` filters out rows where ``is_deleted=1``.

    .. seealso:: :class:`.MergeTree` - for non-deduplicated append-only tables.
    """

    version: str | None = None
    is_deleted: str | None = None
    _name: str = field(default="ReplacingMergeTree", init=False)

    def _engine_head(self) -> str:
        args = [a for a in (self.version, self.is_deleted) if a is not None]
        return "ReplacingMergeTree" + (f"({', '.join(args)})" if args else "")


@dataclass(frozen=True)
class AggregatingMergeTree(_Engine):
    """AggregatingMergeTree engine - merges rows by aggregating AggregateFunction columns."""

    _name: str = field(default="AggregatingMergeTree", init=False)
