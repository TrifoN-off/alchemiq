"""`import alchemiq.health` must never pull in an optional extra."""

from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


def test_import_health_does_not_pull_extras() -> None:
    code = (
        "import sys, alchemiq.health; "
        "bad = ('fastapi', 'clickhouse_connect', 'clickhouse_sqlalchemy', 'redis'); "
        "leaked = [m for m in sys.modules "
        "if any(m == b or m.startswith(b + '.') for b in bad)]; "
        "assert not leaked, leaked"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_top_level_check_health_does_not_pull_extras() -> None:
    code = (
        "import sys, alchemiq; "
        "assert hasattr(alchemiq, 'check_health'); "
        "bad = ('fastapi', 'clickhouse_connect', 'clickhouse_sqlalchemy', 'redis'); "
        "leaked = [m for m in sys.modules "
        "if any(m == b or m.startswith(b + '.') for b in bad)]; "
        "assert not leaked, leaked"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
