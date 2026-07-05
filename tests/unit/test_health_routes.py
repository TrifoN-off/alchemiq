from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

import alchemiq.fastapi.health as health_mod
from alchemiq.fastapi import health_router
from alchemiq.health import ComponentHealth, HealthReport

pytestmark = pytest.mark.unit


def _client_for(report: HealthReport, monkeypatch) -> httpx.AsyncClient:
    async def fake_check_health(*, timeout: float = 5.0) -> HealthReport:
        return report

    monkeypatch.setattr(health_mod, "check_health", fake_check_health)
    app = FastAPI()
    app.include_router(health_router())
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_ready_healthy_returns_200(monkeypatch) -> None:
    report = HealthReport(True, (ComponentHealth("postgres", True, 1.2),))
    async with _client_for(report, monkeypatch) as c:
        resp = await c.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["checks"][0]["name"] == "postgres"


async def test_ready_unhealthy_returns_503(monkeypatch) -> None:
    report = HealthReport(False, (ComponentHealth("cache", False, None, "down"),))
    async with _client_for(report, monkeypatch) as c:
        resp = await c.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json()["status"] == "unhealthy"


async def test_live_always_200() -> None:
    app = FastAPI()
    app.include_router(health_router())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "alive"}


async def test_liveness_can_be_disabled() -> None:
    app = FastAPI()
    app.include_router(health_router(include_liveness=False))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.get("/health/live")
    assert resp.status_code == 404


def test_custom_prefix() -> None:
    router = health_router(prefix="/probe")
    paths = {r.path for r in router.routes}  # type: ignore[attr-defined]
    assert "/probe/ready" in paths
    assert "/probe/live" in paths
