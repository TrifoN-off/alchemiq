"""PersistenceError -> HTTP status mapping."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException

from alchemiq.exceptions import (
    EngineNotConfiguredError,
    MultipleResultsFound,
    NotFoundError,
    PersistenceError,
    RelationNotLoaded,
)
from alchemiq.fastapi.errors import (
    http_exception_for,
    install_exception_handlers,
    status_for,
)

pytestmark = pytest.mark.unit


def test_status_for_known_mappings() -> None:
    assert status_for(NotFoundError("x")) == 404
    assert status_for(MultipleResultsFound("x")) == 409
    assert status_for(RelationNotLoaded("x")) == 500


def test_status_for_unknown_persistence_error_defaults_500() -> None:
    assert status_for(EngineNotConfiguredError("x")) == 500


def test_http_exception_for_carries_status_and_detail() -> None:
    exc = http_exception_for(NotFoundError("nope"))
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 404
    assert exc.detail == "nope"


def test_install_registers_persistence_error_handler() -> None:
    app = FastAPI()
    install_exception_handlers(app)
    assert PersistenceError in app.exception_handlers


async def test_concurrent_modification_returns_409_over_http() -> None:
    import httpx

    from alchemiq import ConcurrentModificationError
    from alchemiq.fastapi.errors import install_exception_handlers

    app = FastAPI()
    install_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> dict[str, str]:
        raise ConcurrentModificationError("stale")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.get("/boom")
    assert resp.status_code == 409
    assert resp.json()["detail"] == "stale"
