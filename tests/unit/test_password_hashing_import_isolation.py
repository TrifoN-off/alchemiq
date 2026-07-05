from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


def test_import_alchemiq_does_not_import_argon2_or_bcrypt() -> None:
    code = (
        "import sys, alchemiq; "
        "leaked = [m for m in sys.modules "
        "if m in ('argon2', 'bcrypt') or m.startswith(('argon2.', 'bcrypt.'))]; "
        "assert not leaked, leaked"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
