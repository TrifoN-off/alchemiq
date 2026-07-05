"""CRUD router factory for alchemiq models."""

from collections.abc import Sequence
from enum import Enum
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from alchemiq.exceptions import ConfigError, InvalidCursorError, NotFoundError
from alchemiq.fastapi import schemas as _schemas
from alchemiq.fastapi.deps import resolve_repository
from alchemiq.model.serialization import to_dict
from alchemiq.query import Q
from alchemiq.runtime.unit_of_work import UnitOfWork

_ALL_ENDPOINTS = frozenset({"list", "read", "create", "update", "delete"})


def crud_router(
    repository: Any,
    *,
    prefix: str = "",
    tags: list[str | Enum] | None = None,
    read_schema: type[BaseModel] | None = None,
    create_schema: type[BaseModel] | None = None,
    update_schema: type[BaseModel] | None = None,
    endpoints: set[str] | None = None,
    pagination: Literal["offset", "cursor"] = "offset",
    dependencies: Sequence[Any] | None = None,
    filter_allow: set[str] | None = None,
    id_type: type = int,
) -> APIRouter:
    """Build a FastAPI ``APIRouter`` with standard CRUD endpoints for an alchemiq model.

    ``repository`` may be a :class:`.Repository` instance, subclass, or a bare model class.
    By default all five endpoints are mounted:

    - ``GET /`` - paginated list (offset or cursor)
    - ``GET /{id}`` - single read (404 if missing)
    - ``POST /`` - create, returns 201 with the created resource
    - ``PATCH /{id}`` - partial update (only supplied fields are changed)
    - ``DELETE /{id}`` - soft or hard delete, returns 204 with no body

    Pass ``endpoints={"list", "read"}`` to mount a subset.  ``pagination="cursor"`` switches
    the list endpoint to keyset pagination (``after``/``before`` query params) returning a
    ``CursorPage`` envelope instead of the default offset ``Page`` envelope.

    Pydantic schemas are auto-derived from the model's field metadata via
    :func:`.read_schema`, :func:`.create_schema`, and :func:`.update_schema`; pass
    explicit schemas to override.

    E.g.::

        from fastapi import Depends, FastAPI
        from alchemiq import Repository
        from alchemiq.fastapi import crud_router, install_exception_handlers

        app = FastAPI()
        install_exception_handlers(app)
        app.include_router(crud_router(User, prefix="/users"))

        # Subset of endpoints with cursor pagination and auth dependency:
        app.include_router(
            crud_router(
                Repository(Article),
                prefix="/articles",
                tags=["articles"],
                dependencies=[Depends(require_token)],
                endpoints={"list", "read", "create"},
                pagination="cursor",
            )
        )

    :param repository: a :class:`.Repository` instance, subclass, or bare model class.
    :param prefix: URL prefix for all routes (e.g. ``"/items"``).
    :param tags: OpenAPI tags applied to every route.
    :param read_schema: override the auto-derived read (response) Pydantic schema.
    :param create_schema: override the auto-derived create (request body) schema.
    :param update_schema: override the auto-derived partial-update schema.
    :param endpoints: subset of ``{"list", "read", "create", "update", "delete"}`` to mount;
        defaults to all five.
    :param pagination: ``"offset"`` (default) or ``"cursor"`` for the list endpoint.
    :param dependencies: FastAPI dependencies applied to every route.
    :param filter_allow: allowlist of field names the ``q`` query param may filter on.
    :param id_type: Python type used to parse the ``{id}`` path parameter (default ``int``).
    :return: a configured ``APIRouter`` ready to pass to ``app.include_router()``.
    :raises ConfigError: if ``endpoints`` contains an unknown name.

    .. seealso:: :func:`.install_exception_handlers` - wire ``PersistenceError`` -> HTTP.
    """
    repo = resolve_repository(repository)
    model = repo.model

    selected = _ALL_ENDPOINTS if endpoints is None else frozenset(endpoints)
    unknown = selected - _ALL_ENDPOINTS
    if unknown:
        raise ConfigError(f"Unknown endpoint(s): {sorted(unknown)}")

    read = read_schema or _schemas.read_schema(model)
    create = create_schema or _schemas.create_schema(model)
    update = update_schema or _schemas.update_schema(model)
    page = _schemas.page_schema(read)
    pk = _schemas.pk_name(model)
    label = model.__name__.lower()

    router = APIRouter(prefix=prefix, tags=tags, dependencies=dependencies)

    def _serialize(obj: Any) -> Any:
        return read.model_validate(to_dict(obj, mode="json"))

    if "list" in selected and pagination == "cursor":
        cursor_page = _schemas.cursor_page_schema(read)

        @router.get("/", response_model=cursor_page, name=f"{label}_list")
        async def list_cursor(
            after: str | None = Query(None),
            before: str | None = Query(None),
            size: int = Query(20, ge=1, le=200),
            order_by: str | None = Query(None),
            q: str | None = Query(None),
        ) -> Any:
            qs = repo
            if q is not None:
                try:
                    parsed = Q.from_base64(q, model, allow=filter_allow)
                except Exception as exc:
                    raise HTTPException(
                        status_code=400, detail=f"Invalid q parameter: {exc}"
                    ) from exc
                qs = qs.filter(parsed)
            if order_by:
                fields = [f.strip() for f in order_by.split(",") if f.strip()]
                if fields:
                    qs = qs.order_by(*fields)
            try:
                result = await qs.cursor_paginate(size=size, after=after, before=before)
            except (InvalidCursorError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=f"Invalid cursor: {exc}") from exc
            return cursor_page(
                items=[_serialize(r) for r in result.items],
                next_cursor=result.next_cursor,
                prev_cursor=result.prev_cursor,
                has_next=result.has_next,
                has_prev=result.has_prev,
            )

    elif "list" in selected:

        @router.get("/", response_model=page, name=f"{label}_list")
        async def list_(
            page_: int = Query(1, alias="page", ge=1),
            size: int = Query(20, ge=1, le=200),
            order_by: str | None = Query(None),
            q: str | None = Query(None),
        ) -> Any:
            qs = repo
            if q is not None:
                try:
                    parsed = Q.from_base64(q, model, allow=filter_allow)
                except Exception as exc:
                    raise HTTPException(
                        status_code=400, detail=f"Invalid q parameter: {exc}"
                    ) from exc
                qs = qs.filter(parsed)
            if order_by:
                fields = [f.strip() for f in order_by.split(",") if f.strip()]
                if fields:
                    qs = qs.order_by(*fields)
            result = await qs.paginate(page=page_, size=size)
            return page(
                items=[_serialize(r) for r in result.items],
                total=result.total,
                page=result.page,
                size=result.size,
                pages=result.pages,
                has_next=result.has_next,
                has_prev=result.has_prev,
            )

    if "read" in selected:

        @router.get("/{item_id}", response_model=read, name=f"{label}_read")
        async def read_(item_id: id_type) -> Any:  # ty: ignore[invalid-type-form]
            try:
                obj = await repo.get(**{pk: item_id})
            except NotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return _serialize(obj)

    if "create" in selected:

        @router.post(
            "/",
            response_model=read,
            status_code=status.HTTP_201_CREATED,
            name=f"{label}_create",
        )
        async def create_(body: create) -> Any:  # ty: ignore[invalid-type-form]
            async with UnitOfWork():
                obj = await repo.create(**body.model_dump())
            return _serialize(obj)

    if "update" in selected:

        @router.patch("/{item_id}", response_model=read, name=f"{label}_update")
        async def update_(item_id: id_type, body: update) -> Any:  # ty: ignore[invalid-type-form]
            changes = body.model_dump(exclude_unset=True)
            try:
                async with UnitOfWork():
                    obj = await repo.update(item_id, **changes)
            except NotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return _serialize(obj)

    if "delete" in selected:

        @router.delete(
            "/{item_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            name=f"{label}_delete",
        )
        async def delete_(item_id: id_type) -> None:  # ty: ignore[invalid-type-form]
            try:
                async with UnitOfWork():
                    await repo.delete(item_id)
            except NotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router
