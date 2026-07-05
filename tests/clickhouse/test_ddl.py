import datetime as dt

import pytest

from alchemiq.clickhouse import ClickHouseModel, MergeTree
from alchemiq.clickhouse.ddl import _column_defs, create_table_sql
from alchemiq.clickhouse.types import DateTime64, UInt32


class _Hit(ClickHouseModel):
    event_time: dt.datetime = DateTime64(3)
    user_id: int = UInt32()
    url: str

    class Meta:
        engine = MergeTree(order_by=("event_time", "user_id"), partition_by="toYYYYMM(event_time)")


@pytest.mark.unit
def test_create_table_sql_has_columns_and_engine():
    sql = create_table_sql(_Hit)
    assert sql.startswith("CREATE TABLE")
    assert "_hit" in sql
    assert "user_id UInt32" in sql
    assert "event_time DateTime64(3)" in sql
    assert "url String" in sql
    assert "ENGINE = MergeTree ORDER BY (event_time, user_id)" in sql
    assert "PARTITION BY toYYYYMM(event_time)" in sql


@pytest.mark.unit
def test_column_defs_are_exact():
    defs = [line.strip().rstrip(",") for line in _column_defs(_Hit).splitlines()]
    assert defs == ["event_time DateTime64(3)", "user_id UInt32", "url String"]
