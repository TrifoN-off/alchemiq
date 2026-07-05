"""`import alchemiq` must never pull in FastAPI; the subpackage may."""

from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


def test_import_alchemiq_does_not_import_fastapi() -> None:
    code = (
        "import sys, alchemiq; "
        "leaked = [m for m in sys.modules if m == 'fastapi' or m.startswith('fastapi.')]; "
        "assert not leaked, leaked"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_fastapi_subpackage_is_importable() -> None:
    import alchemiq.fastapi  # noqa: F401
