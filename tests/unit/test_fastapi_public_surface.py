"""Public surface of alchemiq.fastapi; and not leaked to top-level alchemiq."""

from __future__ import annotations

import pytest

import alchemiq
import alchemiq.fastapi as afa

pytestmark = pytest.mark.unit

_EXPECTED_EXPORTS = {
    "crud_router",
    "health_router",
    "lifespan",
    "repository",
    "unit_of_work",
    "db_session",
    "install_exception_handlers",
    "http_exception_for",
    "status_for",
    "read_schema",
    "create_schema",
    "update_schema",
    "page_schema",
    "cursor_page_schema",
    "pk_name",
}


def test_public_exports_present() -> None:
    assert set(afa.__all__) == _EXPECTED_EXPORTS
    for name in afa.__all__:
        assert hasattr(afa, name), name


def test_not_reexported_at_top_level() -> None:
    assert not hasattr(alchemiq, "crud_router")
    assert "crud_router" not in alchemiq.__all__
