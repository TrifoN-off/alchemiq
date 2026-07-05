"""Capstone: full app wiring - auth dependency, error handler, endpoint toggle."""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI, Header, HTTPException

from alchemiq import Model, Repository
from alchemiq.fastapi import crud_router, install_exception_handlers
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class FapiE2ERow(Model):
    __tablename__ = "fapi_e2e_row"
    id: PK[int]
    name: str


class FapiE2ERepo(Repository[FapiE2ERow]):
    pass


async def require_token(x_token: str = Header(default="")) -> None:
    if x_token != "secret":
        raise HTTPException(status_code=401, detail="bad token")


@pytest_asyncio.fixture
async def client(configured_db):
    app = FastAPI()
    install_exception_handlers(app)
    app.include_router(
        crud_router(
            FapiE2ERepo,
            prefix="/items",
            tags=["items"],
            dependencies=[Depends(require_token)],
            endpoints={"list", "read", "create"},  # no update/delete
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def test_auth_gate_blocks_without_token(client) -> None:
    resp = await client.post("/items/", json={"name": "x"})
    assert resp.status_code == 401


async def test_create_and_read_with_token(client) -> None:
    headers = {"x-token": "secret"}
    created = await client.post("/items/", json={"name": "ok"}, headers=headers)
    assert created.status_code == 201
    item_id = created.json()["id"]
    fetched = await client.get(f"/items/{item_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "ok"


async def test_disabled_endpoint_returns_405(client) -> None:
    resp = await client.delete("/items/1", headers={"x-token": "secret"})
    assert resp.status_code == 405  # delete not registered


async def test_missing_read_returns_404(client) -> None:
    resp = await client.get("/items/999", headers={"x-token": "secret"})
    assert resp.status_code == 404
    assert resp.json()["detail"]


async def test_installed_handler_maps_raw_persistence_error() -> None:
    from alchemiq.exceptions import MultipleResultsFound

    app = FastAPI()
    install_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise MultipleResultsFound("two found")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get("/boom")
    assert resp.status_code == 409
    assert resp.json()["detail"] == "two found"
