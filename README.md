# alchemiq

The data layer for async FastAPI microservices: Django-style models, transactional
outbox, caching, and ClickHouse - built on SQLAlchemy 2.0.

[![PyPI version](https://img.shields.io/pypi/v/alchemiq)](https://pypi.org/project/alchemiq/)
[![Python](https://img.shields.io/pypi/pyversions/alchemiq)](https://pypi.org/project/alchemiq/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docs](https://readthedocs.org/projects/alchemiq/badge/?version=latest)](https://alchemiq.readthedocs.io)
[![CI](https://github.com/TrifoN-off/alchemiq/actions/workflows/ci.yml/badge.svg)](https://github.com/TrifoN-off/alchemiq/actions)

---

## 30-second example

```python
import alchemiq
from alchemiq import Model, Repository
from alchemiq.types import PK, Email

class User(Model):
    id: PK[int]
    name: str
    email: Email

alchemiq.configure("postgresql+asyncpg://user:password@localhost/mydb")
await alchemiq.create_all()

users = Repository(User)
user  = await users.create(name="Ada Lovelace", email="ada@example.com")
found = await users.get(id=user.id)
print(found.name)  # Ada Lovelace
```

---

## Features

- **Async PostgreSQL and ClickHouse** - a single query DSL covers both backends.
- **Django-flavoured models** - declare fields with plain type annotations; `Q` objects, `QuerySet`
  chaining, `order_by`, `limit`, and `offset` work exactly as you would expect.
- **Repository + UnitOfWork** - full CRUD, bulk operations, cursor/keyset pagination, and
  aggregations (`Count`, `Sum`, `Avg`, `Min`, `Max`) out of the box.
- **Soft-delete and optimistic locking** - opt in per model via a `Meta` class.
- **Signals** - async pre/post hooks for create, update, and delete lifecycle events.
- **Serialization** - `to_dict`, `to_schema`, `to_pydantic` with field inclusion/exclusion.
- **Outbox + Relay** - atomic event capture in the same transaction, published to any broker
  (RabbitMQ, Kafka, NATS) via TaskIQ or FastStream.
- **FastAPI integration** - auto-generated CRUD router, DI-ready repository and UoW providers,
  Pydantic schema generation, and a `/health/ready` · `/health/live` router.
- **FastStream consumer DI** - inject sessions, UoW, and repositories into message handlers.
- **Redis caching** - per-repository cache with automatic invalidation on write.
- **Migrations** - Alembic wrapper for PostgreSQL; a custom engine for ClickHouse.
- **Scaffolding** - `alchemiq init` generates a production-ready layered project skeleton.

---

## Installation

```bash
pip install "alchemiq[all]"
```

| Extra | Installs |
|---|---|
| `email` | `email-validator` |
| `phone` | `phonenumbers` |
| `argon2` | `argon2-cffi` |
| `bcrypt` | `bcrypt` (not in `all`) |
| `crypto` | `cryptography` |
| `outbox` | `taskiq`, `taskiq-aio-pika` |
| `fastapi` | `fastapi` |
| `faststream` | `faststream` |
| `redis` | `redis` |
| `postgres` | `asyncpg` (the PostgreSQL driver) |
| `clickhouse` | `clickhouse-connect[async]`, `clickhouse-sqlalchemy` |
| `migrations` | `alembic` |
| `all` | all of the above except `bcrypt` |

---

## Documentation

Full guide and API reference: **<https://alchemiq.readthedocs.io>**

---

## Links

- Source: <https://github.com/TrifoN-off/alchemiq>
- Changelog: [CHANGELOG.md](CHANGELOG.md)
- License: MIT - see [LICENSE](LICENSE)

---

## What's not in v1

`alchemiq` v1 does not include a visual admin, MySQL/SQLite support, synchronous mode,
multi-database routing, audit logs, geolocation fields, or file-field storage adapters.

See the [What's not in v1](https://alchemiq.readthedocs.io/en/latest/guide/whats-not-in-v1.html) guide
for the full list and the reasoning behind each deferral.
