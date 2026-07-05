"""Exception-to-HTTP mapping for alchemiq persistence errors."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from alchemiq.exceptions import (
    ConcurrentModificationError,
    MultipleResultsFound,
    NotFoundError,
    PersistenceError,
    RelationNotLoaded,
)

_STATUS: dict[type[PersistenceError], int] = {
    NotFoundError: 404,
    MultipleResultsFound: 409,
    ConcurrentModificationError: 409,
    RelationNotLoaded: 500,
}


def status_for(exc: PersistenceError) -> int:
    """Return the HTTP status code for a ``PersistenceError``.

    The mapping is:

    - ``NotFoundError`` -> 404
    - ``MultipleResultsFound`` -> 409
    - ``ConcurrentModificationError`` -> 409
    - ``RelationNotLoaded`` -> 500
    - any other ``PersistenceError`` subtype -> 500 (fallback)

    ``InvalidCursorError`` is **not** in this map - :func:`.crud_router` raises it
    directly as an ``HTTPException`` with status 400.

    :param exc: a ``PersistenceError`` (or subclass) instance.
    :return: the HTTP status code integer.
    """
    for exc_type, status in _STATUS.items():
        if isinstance(exc, exc_type):
            return status
    return 500


def http_exception_for(exc: PersistenceError) -> HTTPException:
    """Convert a ``PersistenceError`` to an ``HTTPException`` with the mapped status code.

    :param exc: a ``PersistenceError`` (or subclass) instance.
    :return: an ``HTTPException`` whose ``status_code`` is determined by :func:`.status_for`
        and whose ``detail`` is the string representation of *exc*.
    """
    return HTTPException(status_code=status_for(exc), detail=str(exc))


def install_exception_handlers(app: FastAPI) -> None:
    """Register a global handler that converts ``PersistenceError`` to JSON responses.

    Attaches a single ``app.add_exception_handler`` for ``PersistenceError``.  Each
    subtype is mapped to an HTTP status by :func:`.status_for`; the response body is
    ``{"detail": "<exception message>"}``.

    E.g.::

        from fastapi import FastAPI
        from alchemiq.fastapi import install_exception_handlers, crud_router

        app = FastAPI()
        install_exception_handlers(app)
        app.include_router(crud_router(User, prefix="/rows"))

    :param app: the ``FastAPI`` application instance.

    .. note::

        ``InvalidCursorError`` is **not** caught by this handler.  The list endpoint in
        :func:`.crud_router` raises it as an ``HTTPException(400)`` directly.

    .. seealso:: :func:`.status_for` - the exception->status mapping.
    """

    async def _handle(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, PersistenceError)
        return JSONResponse(status_code=status_for(exc), content={"detail": str(exc)})

    app.add_exception_handler(PersistenceError, _handle)
