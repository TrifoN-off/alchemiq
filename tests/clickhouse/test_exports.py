import pytest

import alchemiq.clickhouse as chmod


@pytest.mark.unit
def test_public_surface_present():
    expected = {
        "ClickHouseModel",
        "ClickHouseRepository",
        "BufferedInserter",
        "MergeTree",
        "ReplacingMergeTree",
        "AggregatingMergeTree",
        "ClickHousePublisher",
        "configure_clickhouse",
        "dispose_clickhouse",
        "is_clickhouse_configured",
        "create_clickhouse_tables",
        "drop_clickhouse_tables",
        "optimize",
        "UInt8",
        "UInt16",
        "UInt32",
        "UInt64",
        "Int8",
        "Int16",
        "Int32",
        "Int64",
        "Float32",
        "Float64",
        "LowCardinality",
        "DateTime64",
        "Enum8",
    }
    assert expected <= set(chmod.__all__)
    for name in expected:
        assert hasattr(chmod, name)


@pytest.mark.unit
def test_not_reexported_at_top_level():
    import alchemiq

    assert "ClickHouseModel" not in alchemiq.__all__
