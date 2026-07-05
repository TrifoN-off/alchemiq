"""FastAPI integration for alchemiq. Requires the ``[fastapi]`` extra."""

from alchemiq.fastapi.deps import db_session, repository, unit_of_work
from alchemiq.fastapi.errors import (
    http_exception_for,
    install_exception_handlers,
    status_for,
)
from alchemiq.fastapi.health import health_router
from alchemiq.fastapi.lifespan import lifespan
from alchemiq.fastapi.router import crud_router
from alchemiq.fastapi.schemas import (
    create_schema,
    cursor_page_schema,
    page_schema,
    pk_name,
    read_schema,
    update_schema,
)

__all__ = [
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
]
