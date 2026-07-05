from __future__ import annotations

import pytest

import alchemiq
import alchemiq.faststream as afs

pytestmark = pytest.mark.unit

_EXPECTED_EXPORTS = {
    "FastStreamPublisher",
    "lifespan",
    "repository",
    "unit_of_work",
    "db_session",
}


def test_public_exports_present() -> None:
    assert set(afs.__all__) == _EXPECTED_EXPORTS
    for name in afs.__all__:
        assert hasattr(afs, name), name


def test_not_reexported_at_top_level() -> None:
    assert not hasattr(alchemiq, "FastStreamPublisher")
    assert "FastStreamPublisher" not in alchemiq.__all__
