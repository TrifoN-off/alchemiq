"""Write endpoints over a real ASGI app + PostgreSQL: create/update/delete + soft-delete."""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from alchemiq import Model
from alchemiq.fastapi import crud_router, install_exception_handlers
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class FapiWriteRow(Model):
    __tablename__ = "fapi_write_row"
    id: PK[int]
    name: str
    note: str | None


class FapiSoftRow(Model):
    __tablename__ = "fapi_write_soft_row"
    id: PK[int]
    name: str

    class Meta:
        soft_delete = True


def _app() -> FastAPI:
    app = FastAPI()
    install_exception_handlers(app)
    app.include_router(crud_router(FapiWriteRow, prefix="/rows"))
    app.include_router(crud_router(FapiSoftRow, prefix="/soft"))
    return app


@pytest_asyncio.fixture
async def client(configured_db):
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def test_create_returns_201_and_body(client) -> None:
    resp = await client.post("/rows/", json={"name": "alpha", "note": None})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "alpha"
    assert isinstance(body["id"], int)


async def test_create_then_read_roundtrip(client) -> None:
    created = (await client.post("/rows/", json={"name": "beta", "note": "x"})).json()
    fetched = await client.get(f"/rows/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "beta"


async def test_partial_update_only_touches_sent_fields(client) -> None:
    created = (await client.post("/rows/", json={"name": "gamma", "note": "keep"})).json()
    resp = await client.patch(f"/rows/{created['id']}", json={"name": "gamma2"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "gamma2"
    assert body["note"] == "keep"  # untouched (exclude_unset)


async def test_update_missing_returns_404(client) -> None:
    resp = await client.patch("/rows/999", json={"name": "z"})
    assert resp.status_code == 404


async def test_delete_returns_204_then_404(client) -> None:
    created = (await client.post("/rows/", json={"name": "delta", "note": None})).json()
    assert (await client.delete(f"/rows/{created['id']}")).status_code == 204
    assert (await client.get(f"/rows/{created['id']}")).status_code == 404


async def test_delete_missing_returns_404(client) -> None:
    assert (await client.delete("/rows/999")).status_code == 404


async def test_soft_delete_tombstones_then_absent(client) -> None:
    created = (await client.post("/soft/", json={"name": "ghost"})).json()
    assert (await client.delete(f"/soft/{created['id']}")).status_code == 204
    assert (await client.get(f"/soft/{created['id']}")).status_code == 404
    listing = (await client.get("/soft/")).json()
    assert all(r["id"] != created["id"] for r in listing["items"])
