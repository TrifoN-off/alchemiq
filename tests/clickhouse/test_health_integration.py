from __future__ import annotations

import pytest

from alchemiq import check_health

pytestmark = pytest.mark.clickhouse


async def test_clickhouse_healthy(configured_clickhouse) -> None:
    report = await check_health()
    ch = next(c for c in report.components if c.name == "clickhouse")
    assert ch.healthy is True
    assert ch.latency_ms is not None
    assert report.healthy is True
