"""Router construction: endpoint toggles, unknown-name guard, bad-q -> 400."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from alchemiq import Model
from alchemiq.exceptions import ConfigError
from alchemiq.fastapi.router import crud_router
from alchemiq.types import PK

pytestmark = pytest.mark.unit


class FapiCfgRow(Model):
    __tablename__ = "fapi_cfg_row"
    id: PK[int]
    name: str


def test_unknown_endpoint_name_raises() -> None:
    with pytest.raises(ConfigError):
        crud_router(FapiCfgRow, endpoints={"list", "frobnicate"})


def test_endpoints_toggle_registers_only_requested() -> None:
    router = crud_router(FapiCfgRow, endpoints={"read"})
    methods = {m for route in router.routes for m in route.methods}
    assert "GET" in methods
    assert "POST" not in methods and "DELETE" not in methods


async def test_bad_base64_q_returns_400() -> None:
    app = FastAPI()
    app.include_router(crud_router(FapiCfgRow, endpoints={"list"}, prefix="/cfg"))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get("/cfg/", params={"q": "!!!not-base64!!!"})
    assert resp.status_code == 400
