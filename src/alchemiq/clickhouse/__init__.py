"""ClickHouse support (behind the [clickhouse] extra)."""

from alchemiq.clickhouse.connection import (
    configure_clickhouse,
    dispose_clickhouse,
    is_clickhouse_configured,
)
from alchemiq.clickhouse.ddl import (
    create_clickhouse_tables,
    drop_clickhouse_tables,
    optimize,
)
from alchemiq.clickhouse.engines import (
    AggregatingMergeTree,
    MergeTree,
    ReplacingMergeTree,
)
from alchemiq.clickhouse.model import ClickHouseModel
from alchemiq.clickhouse.publisher import ClickHousePublisher
from alchemiq.clickhouse.repository import BufferedInserter, ClickHouseRepository
from alchemiq.clickhouse.types import (
    DateTime64,
    Enum8,
    Float32,
    Float64,
    Int8,
    Int16,
    Int32,
    Int64,
    LowCardinality,
    UInt8,
    UInt16,
    UInt32,
    UInt64,
)

__all__ = [
    "AggregatingMergeTree",
    "BufferedInserter",
    "ClickHouseModel",
    "ClickHousePublisher",
    "ClickHouseRepository",
    "DateTime64",
    "Enum8",
    "Float32",
    "Float64",
    "Int16",
    "Int32",
    "Int64",
    "Int8",
    "LowCardinality",
    "MergeTree",
    "ReplacingMergeTree",
    "UInt16",
    "UInt32",
    "UInt64",
    "UInt8",
    "configure_clickhouse",
    "create_clickhouse_tables",
    "dispose_clickhouse",
    "drop_clickhouse_tables",
    "is_clickhouse_configured",
    "optimize",
]
