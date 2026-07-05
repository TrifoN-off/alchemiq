from __future__ import annotations

import pytest

from alchemiq.migrations.clickhouse.migration import Migration
from alchemiq.migrations.clickhouse.operations import Operations

pytestmark = pytest.mark.unit


def test_migration_up_raises_not_implemented() -> None:
    m = Migration()
    with pytest.raises(NotImplementedError):
        m.up(Operations())


def test_migration_down_raises_not_implemented() -> None:
    m = Migration()
    with pytest.raises(NotImplementedError):
        m.down(Operations())
