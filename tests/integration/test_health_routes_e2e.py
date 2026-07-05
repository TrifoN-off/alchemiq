from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from alchemiq.fastapi import health_router

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def client(configured_db):
    app = FastAPI()
    app.include_router(health_router())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_ready_healthy_over_real_pg(client) -> None:
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert any(check["name"] == "postgres" for check in body["checks"])


async def test_live_over_real_app(client) -> None:
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "alive"}
