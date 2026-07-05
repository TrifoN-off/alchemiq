from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from alchemiq.health.report import ComponentHealth, HealthReport

pytestmark = pytest.mark.unit


def test_component_health_is_frozen() -> None:
    c = ComponentHealth("postgres", True, 1.5)
    assert c.error is None
    with pytest.raises(FrozenInstanceError):
        c.healthy = False  # type: ignore[misc]  # frozen


def test_to_dict_healthy_shape() -> None:
    report = HealthReport(
        healthy=True,
        components=(ComponentHealth("postgres", True, 1.5),),
    )
    assert report.to_dict() == {
        "status": "healthy",
        "checks": [
            {"name": "postgres", "healthy": True, "latency_ms": 1.5, "error": None},
        ],
    }


def test_to_dict_unhealthy_with_error() -> None:
    report = HealthReport(
        healthy=False,
        components=(
            ComponentHealth("postgres", True, 1.5),
            ComponentHealth("cache", False, None, "ConnectionError: down"),
        ),
    )
    d = report.to_dict()
    assert d["status"] == "unhealthy"
    assert d["checks"][1] == {
        "name": "cache",
        "healthy": False,
        "latency_ms": None,
        "error": "ConnectionError: down",
    }


def test_to_dict_no_components() -> None:
    assert HealthReport(healthy=True, components=()).to_dict() == {
        "status": "healthy",
        "checks": [],
    }
