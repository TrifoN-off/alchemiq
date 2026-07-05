"""Read endpoints over a real ASGI app + PostgreSQL."""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from alchemiq import Model, Q, Repository
from alchemiq.fastapi import crud_router, install_exception_handlers
from alchemiq.runtime.session import session_scope
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class FapiReadRow(Model):
    __tablename__ = "fapi_read_row"
    id: PK[int]
    name: str


class FapiReadRepo(Repository[FapiReadRow]):
    pass


@pytest_asyncio.fixture
async def client(configured_db):
    async with session_scope(write=True) as s:
        s.add_all([FapiReadRow(id=i, name=f"n{i}") for i in range(1, 6)])
    app = FastAPI()
    install_exception_handlers(app)
    app.include_router(crud_router(FapiReadRepo, prefix="/rows"))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def test_list_paginates(client) -> None:
    resp = await client.get("/rows/", params={"page": 2, "size": 2, "order_by": "id"})
    assert resp.status_code == 200
    body = resp.json()
    assert [r["id"] for r in body["items"]] == [3, 4]
    assert body["total"] == 5
    assert body["pages"] == 3
    assert body["has_next"] is True
    assert body["has_prev"] is True


async def test_list_filters_by_base64_q(client) -> None:
    q = Q(name="n3").to_base64()
    resp = await client.get("/rows/", params={"q": q})
    assert resp.status_code == 200
    body = resp.json()
    assert [r["name"] for r in body["items"]] == ["n3"]


async def test_read_one(client) -> None:
    resp = await client.get("/rows/2")
    assert resp.status_code == 200
    assert resp.json() == {"id": 2, "name": "n2"}


async def test_read_missing_returns_404(client) -> None:
    resp = await client.get("/rows/999")
    assert resp.status_code == 404


async def test_read_bad_path_type_returns_422(client) -> None:
    resp = await client.get("/rows/not-an-int")
    assert resp.status_code == 422
