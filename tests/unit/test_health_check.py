from __future__ import annotations

import pytest

import alchemiq.health.checks as checks
from alchemiq.health import ComponentHealth, HealthReport, check_health

pytestmark = pytest.mark.unit


# --- orchestration (check_health) ---


async def test_nothing_configured_is_healthy(monkeypatch) -> None:
    monkeypatch.setattr(checks, "is_configured", lambda: False)
    monkeypatch.setattr(checks, "_clickhouse_configured", lambda: False)
    monkeypatch.setattr(checks, "get_cache", lambda: None)
    report = await check_health()
    assert isinstance(report, HealthReport)
    assert report.healthy is True
    assert report.components == ()


async def test_only_configured_backends_probed(monkeypatch) -> None:
    monkeypatch.setattr(checks, "is_configured", lambda: True)
    monkeypatch.setattr(checks, "_clickhouse_configured", lambda: False)
    monkeypatch.setattr(checks, "get_cache", lambda: None)

    async def fake_pg(timeout: float) -> ComponentHealth:
        return ComponentHealth("postgres", True, 1.0)

    monkeypatch.setattr(checks, "_probe_postgres", fake_pg)
    report = await check_health()
    assert [c.name for c in report.components] == ["postgres"]
    assert report.healthy is True


async def test_any_unhealthy_makes_overall_unhealthy(monkeypatch) -> None:
    monkeypatch.setattr(checks, "is_configured", lambda: True)
    monkeypatch.setattr(checks, "_clickhouse_configured", lambda: False)
    monkeypatch.setattr(checks, "get_cache", lambda: object())

    async def fake_pg(timeout: float) -> ComponentHealth:
        return ComponentHealth("postgres", True, 1.0)

    async def fake_cache(backend: object, timeout: float) -> ComponentHealth:
        return ComponentHealth("cache", False, None, "boom")

    monkeypatch.setattr(checks, "_probe_postgres", fake_pg)
    monkeypatch.setattr(checks, "_probe_cache", fake_cache)
    report = await check_health()
    assert report.healthy is False
    assert {c.name for c in report.components} == {"postgres", "cache"}


# --- individual probes ---


class _SlowConn:
    async def __aenter__(self) -> _SlowConn:
        return self

    async def __aexit__(self, *a: object) -> bool:
        return False

    async def execute(self, *a: object) -> None:
        import asyncio

        await asyncio.sleep(10)


class _SlowEngine:
    def connect(self) -> _SlowConn:
        return _SlowConn()


class _BoomEngine:
    def connect(self) -> object:
        raise RuntimeError("no socket")


async def test_probe_postgres_timeout(monkeypatch) -> None:
    monkeypatch.setattr(checks, "require_engine", lambda: _SlowEngine())
    result = await checks._probe_postgres(timeout=0.01)
    assert result.name == "postgres"
    assert result.healthy is False
    assert result.latency_ms is None


async def test_probe_postgres_error(monkeypatch) -> None:
    monkeypatch.setattr(checks, "require_engine", lambda: _BoomEngine())
    result = await checks._probe_postgres(timeout=1.0)
    assert result.healthy is False
    assert "RuntimeError" in (result.error or "")


class _OkCache:
    async def get(self, key: str) -> str | None:
        return None


class _BoomCache:
    async def get(self, key: str) -> str | None:
        raise ConnectionError("redis down")


async def test_probe_cache_ok() -> None:
    result = await checks._probe_cache(_OkCache(), timeout=1.0)
    assert result.name == "cache"
    assert result.healthy is True
    assert result.latency_ms is not None


async def test_probe_cache_error() -> None:
    result = await checks._probe_cache(_BoomCache(), timeout=1.0)
    assert result.healthy is False
    assert "ConnectionError" in (result.error or "")


class _OkClient:
    async def ping(self) -> bool:
        return True


class _DownClient:
    async def ping(self) -> bool:
        return False


async def test_probe_clickhouse_ok(monkeypatch) -> None:
    async def fake_get() -> _OkClient:
        return _OkClient()

    monkeypatch.setattr("alchemiq.clickhouse.connection.get_clickhouse_client", fake_get)
    result = await checks._probe_clickhouse(timeout=1.0)
    assert result.name == "clickhouse"
    assert result.healthy is True


async def test_probe_clickhouse_ping_false(monkeypatch) -> None:
    async def fake_get() -> _DownClient:
        return _DownClient()

    monkeypatch.setattr("alchemiq.clickhouse.connection.get_clickhouse_client", fake_get)
    result = await checks._probe_clickhouse(timeout=1.0)
    assert result.healthy is False
