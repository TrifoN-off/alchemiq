from __future__ import annotations

import tomllib
from pathlib import Path


def test_package_imports() -> None:
    import alchemiq

    # The version number is bumped by semantic-release (version_toml +
    # version_variables keep pyproject and __init__ in lockstep) - assert the
    # lockstep, never a hardcoded number.
    pyproject = Path(alchemiq.__file__).parent.parent.parent / "pyproject.toml"
    if pyproject.is_file():
        expected = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
        assert alchemiq.__version__ == expected
    assert alchemiq.__version__.count(".") == 2
