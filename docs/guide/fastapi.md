# FastAPI integration

The ``[fastapi]`` extra wires alchemiq into FastAPI: an automatic CRUD router
factory, request-scoped dependency providers, a global exception handler, and a
lifespan helper that manages the database engine.

```bash
pip install "alchemiq[fastapi,postgres]"
```

---

## Exception handler

Register alchemiq's global exception handler once, at app startup, so every
``PersistenceError`` converts to a JSON response automatically:

```python
from fastapi import FastAPI
from alchemiq.fastapi import install_exception_handlers

app = FastAPI()
install_exception_handlers(app)
```

The mapping is:

| Exception | HTTP status |
|---|---|
| ``NotFoundError`` | 404 |
| ``MultipleResultsFound`` | 409 |
| ``ConcurrentModificationError`` | 409 |
| ``RelationNotLoaded`` | 500 |
| any other ``PersistenceError`` | 500 |

``InvalidCursorError`` is **not** caught by this handler - the list endpoint in
``crud_router`` converts it directly to an ``HTTPException(400)``.

---

## Automatic CRUD router

``crud_router`` builds a fully-wired ``APIRouter`` from a model or repository.
By default all five standard endpoints are mounted:

| Method | Path | Description |
|---|---|---|
| ``GET`` | ``/`` | Paginated list |
| ``GET`` | ``/{id}`` | Single-row read (404 if missing) |
| ``POST`` | ``/`` | Create, returns 201 |
| ``PATCH`` | ``/{id}`` | Partial update (unset fields are untouched) |
| ``DELETE`` | ``/{id}`` | Soft or hard delete, returns 204 |

### Minimal example

```python
from fastapi import FastAPI
from alchemiq import Repository
from alchemiq.fastapi import crud_router, install_exception_handlers

app = FastAPI()
install_exception_handlers(app)

app.include_router(crud_router(User, prefix="/users"))
```

``crud_router`` accepts a bare model class, a ``Repository`` instance, or a
``Repository`` subclass.

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| ``repository`` | model or ``Repository`` | *(required)* | Model class or repository to expose |
| ``prefix`` | ``str`` | ``""`` | URL prefix for all routes, e.g. ``"/users"`` |
| ``tags`` | ``list[str]`` | ``None`` | OpenAPI tags applied to every route |
| ``read_schema`` | Pydantic model | auto-derived | Response schema |
| ``create_schema`` | Pydantic model | auto-derived | Create request body schema |
| ``update_schema`` | Pydantic model | auto-derived | Partial-update request body schema |
| ``endpoints`` | ``set[str]`` | all five | Subset of ``{"list", "read", "create", "update", "delete"}`` |
| ``pagination`` | ``"offset"`` or ``"cursor"`` | ``"offset"`` | List endpoint pagination style |
| ``dependencies`` | ``Sequence`` | ``None`` | FastAPI dependencies applied to every route |
| ``filter_allow`` | ``set[str]`` | ``None`` | Allowlist of field names the ``q`` query param may filter on |
| ``id_type`` | type | ``int`` | Python type used to parse the ``{id}`` path parameter |

### Subset of endpoints with cursor pagination

```python
from fastapi import Depends

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
```

``pagination="cursor"`` switches the list endpoint to keyset pagination with
``after`` / ``before`` query parameters.  The response envelope becomes a
``CursorPage`` (``items``, ``next_cursor``, ``prev_cursor``, ``has_next``,
``has_prev``) instead of the default offset ``Page`` (``items``, ``total``,
``page``, ``size``, ``pages``, ``has_next``, ``has_prev``).

### Schema auto-derivation

Pydantic schemas for request bodies and responses are derived automatically from
the model's field metadata.  Pass explicit schemas to override:

```python
app.include_router(
    crud_router(
        User,
        prefix="/users",
        read_schema=UserOut,
        create_schema=UserCreate,
        update_schema=UserPatch,
    )
)
```

---

## Dependency injection

``alchemiq.fastapi`` re-exports the same providers available in
``alchemiq.faststream``.  Use them as ``Depends`` targets to get a session,
repository, or unit of work scoped to each HTTP request:

```python
from fastapi import Depends, FastAPI
from alchemiq import Repository
from alchemiq.fastapi import repository, unit_of_work, db_session

app = FastAPI()

@app.get("/users/{user_id}")
async def get_user(
    user_id: int,
    users: Repository = Depends(repository(User)),
):
    return await users.get(id=user_id)

@app.post("/orders")
async def create_order(
    body: OrderCreate,
    uow=Depends(unit_of_work),
):
    async with uow:
        order = await Repository(Order).create(**body.model_dump())
    return order
```

---

## App lifespan

Use ``lifespan`` from ``alchemiq.fastapi`` to wire the SQLAlchemy engine to the
FastAPI startup/shutdown lifecycle without writing boilerplate:

```python
from fastapi import FastAPI
from alchemiq.fastapi import lifespan
import alchemiq

app = FastAPI(lifespan=lifespan("postgresql+asyncpg://user:pass@localhost/mydb"))
```

The helper calls ``alchemiq.configure(dsn)`` on startup and disposes the engine
on shutdown.
