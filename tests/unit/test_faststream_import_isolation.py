from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


def test_import_alchemiq_does_not_import_faststream() -> None:
    code = (
        "import sys, alchemiq; "
        "leaked = [m for m in sys.modules if m == 'faststream' or m.startswith('faststream.')]; "
        "assert not leaked, leaked"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_faststream_subpackage_is_importable() -> None:
    import alchemiq.faststream  # noqa: F401
