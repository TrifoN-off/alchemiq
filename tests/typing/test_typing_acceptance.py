"""Runs `ty` over the consumer fixture and asserts it is clean.

This is the local TDD signal for the typing-wart fix. mypy + pyright are enforced
by the dedicated CI 'typing' job (they need node / heavier setup); ty is the
project's checker and is always present in the dev environment.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "models.py"


@pytest.mark.unit
def test_ty_clean_on_consumer_fixture():
    ty = shutil.which("ty")
    assert ty is not None, "ty must be installed (dev dependency)"
    result = subprocess.run(
        [ty, "check", str(FIXTURE)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"ty reported diagnostics:\n{result.stdout}\n{result.stderr}"
