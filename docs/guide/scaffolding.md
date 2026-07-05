# Project scaffolding (alchemiq init)

``alchemiq init`` generates a ready-to-run project skeleton: a layer-first
directory structure, an infrastructure configuration (Docker Compose,
``pyproject.toml``), one demonstration model, a smoke-test suite, and
docstring prompts in each layer that tell you exactly what goes there.  The
project starts immediately; you fill in business logic guided by the prompts
in each package's ``__init__.py``.

---

## Single service

```bash
alchemiq init notes
```

Generates ``./notes/`` with a PostgreSQL-backed skeleton:

```
notes/
├── pyproject.toml               # deps (alchemiq extras, uvicorn, faststream) + dev group
├── README.md
├── .env.example                 # copy to .env; commands load it via --env-file
├── .gitignore
├── docker-compose.yml           # postgres / rabbitmq / redis with healthchecks
├── Dockerfile                   # uv-based image, non-root user
├── .dockerignore
├── src/
│   └── notes/
│       ├── __init__.py
│       ├── config.py
│       ├── app.py               # FastAPI application
│       ├── broker.py            # FastStream broker
│       ├── domain/
│       │   ├── __init__.py
│       │   └── models.py        # demonstration model
│       ├── repositories/
│       │   └── __init__.py
│       ├── services/
│       │   └── __init__.py
│       ├── use_cases/
│       │   └── __init__.py
│       └── adapters/
│           ├── http/
│           │   └── __init__.py
│           └── messaging/
│               └── __init__.py
└── tests/
    ├── conftest.py              # optional database fixture (skips without a DSN)
    └── test_models.py           # model smoke test - passes with no database
```

The generated ``pyproject.toml`` pins ``requires-python = ">=3.12"``, depends
on ``alchemiq[fastapi,faststream,redis,postgres,migrations]>=0.1`` (the
backend extra brings the database driver), and carries a ``dev`` dependency
group (``pytest``, ``anyio``, ``ruff``) so ``uv run pytest`` and
``uv run ruff check`` work out of the box.

Each ``__init__.py`` contains a docstring that explains what belongs in that
layer (domain models, repository subclasses, service logic, use-case
orchestration, HTTP or messaging adapters).

### ClickHouse backend

Append ``:clickhouse`` to the service name to switch the primary backend:

```bash
alchemiq init events:clickhouse
```

The skeleton is identical but the model base, migration runner, Docker Compose
service, the test suite, and the ``clickhouse`` dependency extra reflect
ClickHouse instead of PostgreSQL.  The generated tests collect and pass
without any running database.

---

## Monorepo

```bash
alchemiq init myplatform --monorepo users-service analytics:clickhouse
```

Generates a workspace root (``./myplatform/``) containing one
independently-deployable skeleton per service:

```
myplatform/
├── pyproject.toml              # uv workspace + dev dependency group
├── README.md
├── .env.example
├── .gitignore
├── docker-compose.yml          # shared infrastructure with healthchecks
├── docker/
│   └── postgres-init.sh        # creates one database per Postgres service
├── packages/
│   └── shared/                 # cross-service event contracts
└── services/
    ├── users-service/          # Postgres-backed, full layer skeleton
    │   └── src/users_service/...
    └── analytics/              # ClickHouse-backed, full layer skeleton
        └── src/analytics/...
```

Each service under ``services/`` is an independent layer-first skeleton with
its own ``pyproject.toml``, ``Dockerfile``, and tests.  Shared event schemas
and contracts live in ``packages/shared``.  Infrastructure is declared once in
the root ``docker-compose.yml``: containers are included only for what the
workspace actually uses (a ClickHouse container appears only when at least one
service is ClickHouse-backed) and can be trimmed further via ``--without``.

To avoid collisions on the shared Postgres container, every Postgres-backed
service owns a database named after its module (``users_service`` above).
``docker/postgres-init.sh`` creates these databases on the container's first
boot, and each service's ``[tool.alchemiq.postgres]`` and ``config.py`` point
at its own database.

---

## Flags

| Flag | Description |
|---|---|
| ``name:clickhouse`` | Set the primary backend for that service to ClickHouse (default is Postgres) |
| ``--monorepo SERVICE ...`` | Create a monorepo workspace; list each service as ``name[:clickhouse]`` |
| ``--without fastapi,faststream,redis,clickhouse,docker`` | Strip one or more optional layers from the generated skeleton |
| ``--force`` | Write into a non-empty target directory |

### --without examples

```bash
# Minimal service - no FastAPI, no messaging, no Docker files:
alchemiq init worker --without fastapi,faststream,docker

# Postgres service, no Redis layer:
alchemiq init api --without redis
```

``--without`` also removes the matching generated artifacts: dropping
``fastapi`` removes ``app.py`` and ``adapters/http/`` (and the ``uvicorn``
dependency), dropping ``faststream`` removes ``broker.py`` and
``adapters/messaging/`` (and the ``faststream`` dependency), and dropping
``docker`` removes ``docker-compose.yml``, ``Dockerfile``, and
``.dockerignore``.  This applies to ClickHouse-backed services too.

---

## CLI dispatcher

The ``alchemiq`` entry-point acts as a neutral dispatcher:

- ``alchemiq init ...`` is routed to the scaffolder
  (``alchemiq.scaffold.cli``).
- Every other sub-command (``makemigrations``, ``migrate``, ``rollback``,
  ``history``, ``showsql``) is forwarded to the migrations CLI
  (``alchemiq.migrations.cli``).

This means a single installed entry-point handles both project creation and
day-to-day migration management without any namespace conflicts:

```bash
alchemiq init myservice          # scaffold a new project
alchemiq migrate                 # run pending migrations in an existing project
```

---

## After scaffolding

The generated project boots immediately once you install dependencies, create
your ``.env``, and start the infrastructure:

```bash
cd notes
uv sync
cp .env.example .env             # fill in credentials if needed
docker compose up -d             # starts Postgres (and Redis, RabbitMQ if not excluded)
uv run --env-file .env alchemiq makemigrations -m init
uv run --env-file .env alchemiq migrate
uv run --env-file .env uvicorn notes.app:app --reload      # FastAPI dev server
uv run --env-file .env faststream run notes.broker:app     # broker consumer
```

Two things make these commands work as written:

- **``uv run``** executes inside the project venv - installed CLIs such as
  ``alchemiq``, ``uvicorn``, and ``faststream`` are not on your PATH
  otherwise.
- **``--env-file .env``** injects the environment - nothing loads ``.env``
  implicitly, and both the ``alchemiq`` CLI (which interpolates
  ``${POSTGRES_*}`` in ``pyproject.toml``) and ``config.py`` read those
  variables.

In a monorepo, run ``uv sync --all-packages`` at the workspace root, then run
the per-service commands from each ``services/<name>`` directory with
``--env-file ../../.env``.

Run the generated smoke tests any time - they pass without a database:

```bash
uv run pytest
```

From there, fill in each layer following the prompts in each package's
``__init__.py``.
