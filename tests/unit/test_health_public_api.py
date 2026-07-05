from __future__ import annotations

import pytest

import alchemiq

pytestmark = pytest.mark.unit


def test_health_exports_present() -> None:
    assert callable(alchemiq.check_health)
    assert alchemiq.HealthReport is not None
    assert alchemiq.ComponentHealth is not None


def test_health_exports_in_all() -> None:
    for name in ("check_health", "HealthReport", "ComponentHealth"):
        assert name in alchemiq.__all__
