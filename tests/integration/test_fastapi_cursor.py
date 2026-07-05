from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from alchemiq import Model, Repository
from alchemiq.fastapi import crud_router, install_exception_handlers
from alchemiq.runtime.session import session_scope
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class FapiCursorRow(Model):
    __tablename__ = "fapi_cursor_row"
    id: PK[int]
    name: str


class FapiCursorRepo(Repository[FapiCursorRow]):
    pass


@pytest_asyncio.fixture
async def client(configured_db):
    async with session_scope(write=True) as s:
        s.add_all([FapiCursorRow(id=i, name=f"n{i}") for i in range(1, 6)])
    app = FastAPI()
    install_exception_handlers(app)
    app.include_router(
        crud_router(FapiCursorRepo, prefix="/rows", pagination="cursor"),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def test_cursor_first_page(client) -> None:
    resp = await client.get("/rows/", params={"size": 2, "order_by": "id"})
    assert resp.status_code == 200
    body = resp.json()
    assert [r["id"] for r in body["items"]] == [1, 2]
    assert body["has_next"] is True and body["has_prev"] is False
    assert body["next_cursor"] is not None


async def test_cursor_follow_next(client) -> None:
    first = (await client.get("/rows/", params={"size": 2, "order_by": "id"})).json()
    resp = await client.get(
        "/rows/", params={"size": 2, "order_by": "id", "after": first["next_cursor"]}
    )
    body = resp.json()
    assert [r["id"] for r in body["items"]] == [3, 4]
    assert body["has_prev"] is True


async def test_cursor_invalid_returns_400(client) -> None:
    resp = await client.get("/rows/", params={"size": 2, "after": "!!!bad!!!"})
    assert resp.status_code == 400
