import pytest

from alchemiq.clickhouse.engines import (
    AggregatingMergeTree,
    MergeTree,
    ReplacingMergeTree,
)


@pytest.mark.unit
def test_mergetree_clause_basic():
    e = MergeTree(order_by=("event_time", "user_id"))
    assert e.engine_clause() == "ENGINE = MergeTree ORDER BY (event_time, user_id)"


@pytest.mark.unit
def test_mergetree_clause_full():
    e = MergeTree(
        order_by="event_time",
        partition_by="toYYYYMM(event_time)",
        ttl="event_time + INTERVAL 90 DAY",
    )
    assert e.engine_clause() == (
        "ENGINE = MergeTree ORDER BY event_time "
        "PARTITION BY toYYYYMM(event_time) "
        "TTL event_time + INTERVAL 90 DAY"
    )


@pytest.mark.unit
def test_replacing_with_version_and_is_deleted():
    e = ReplacingMergeTree(order_by="key", version="_version", is_deleted="is_deleted")
    assert e.engine_clause() == ("ENGINE = ReplacingMergeTree(_version, is_deleted) ORDER BY key")


@pytest.mark.unit
def test_replacing_version_only():
    e = ReplacingMergeTree(order_by="key", version="ver")
    assert e.engine_clause() == "ENGINE = ReplacingMergeTree(ver) ORDER BY key"


@pytest.mark.unit
def test_aggregating():
    e = AggregatingMergeTree(order_by=("a", "b"))
    assert e.engine_clause() == "ENGINE = AggregatingMergeTree ORDER BY (a, b)"
