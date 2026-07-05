import subprocess
import sys

import pytest


@pytest.mark.unit
def test_import_alchemiq_does_not_import_clickhouse():
    code = (
        "import alchemiq, sys; "
        "assert 'clickhouse_connect' not in sys.modules, 'clickhouse_connect leaked'; "
        "assert 'clickhouse_sqlalchemy' not in sys.modules, 'clickhouse_sqlalchemy leaked'; "
        "print('ok')"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "ok" in out.stdout
