import datetime as dt

import pytest

from alchemiq.clickhouse import ClickHouseModel, MergeTree
from alchemiq.clickhouse.connection import get_clickhouse_client
from alchemiq.clickhouse.types import DateTime64, UInt32


class _DDLRow(ClickHouseModel):
    event_time: dt.datetime = DateTime64(3)
    user_id: int = UInt32()

    class Meta:
        table_name = "_ddl_row"
        engine = MergeTree(order_by=("user_id",))


@pytest.mark.clickhouse
async def test_create_clickhouse_tables_creates_table(configured_clickhouse):
    client = await get_clickhouse_client()
    result = await client.query("EXISTS TABLE _ddl_row")
    assert result.result_rows[0][0] == 1
