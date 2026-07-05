# alchemiq

The data layer for async FastAPI microservices: Django-style models, transactional
outbox, caching, and ClickHouse - built on SQLAlchemy 2.0.

alchemiq is a batteries-included data layer built on SQLAlchemy 2.0's async engine.
It ships the infrastructure every async service otherwise rebuilds by hand -
Django-style models, repositories, Unit of Work, a transactional outbox, caching,
migrations, and health checks - as one coherent, well-tested suite, so you focus on
business logic instead of plumbing.
It targets Python 3.12+, SQLAlchemy 2.0, Pydantic 2, and PostgreSQL (async only).

**Highlights:**

- Async PostgreSQL and ClickHouse - a single query DSL covers both backends.
- Django-flavoured models: declare fields with plain type annotations; `Q` objects, `QuerySet`
  chaining, `order_by`, `limit`, and `offset` work exactly as you would expect.
- {class}`~alchemiq.Repository` + {class}`~alchemiq.UnitOfWork` - full CRUD, bulk operations,
  cursor/keyset pagination, and aggregations (`Count`, `Sum`, `Avg`, `Min`, `Max`) out of the box.
- Soft-delete, signals (pre/post create/update/delete), and optimistic locking - opt in per model
  via a `Meta` class.
- Serialization - `to_dict`, `to_schema`, `to_pydantic` with field inclusion/exclusion.
- Outbox + Relay - atomic event capture in the same transaction, published to RabbitMQ/Kafka/NATS
  via TaskIQ or FastStream.
- FastAPI integration - auto-generated CRUD router, DI-ready repository + UoW providers, Pydantic
  schema generation, and a `/health/ready` · `/health/live` router.
- FastStream consumer DI - inject sessions, UoW, and repositories into message handlers.
- Redis caching - per-repository cache with automatic invalidation on write.
- Migrations - Alembic wrapper for PostgreSQL; a custom engine for ClickHouse.
- Scaffolding - `alchemiq init` generates a production-ready layered project skeleton.

**30-second example:**

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

See the [Getting started](guide/getting-started) guide for the full walkthrough.

```{toctree}
:maxdepth: 2
:caption: Guide

guide/getting-started
guide/models-and-fields
guide/custom-field-types
guide/native-columns
guide/relationships
guide/queries
guide/repository
guide/unit-of-work
guide/soft-delete
guide/signals
guide/optimistic-locking
guide/serialization
guide/fastapi
guide/outbox-and-relay
guide/caching
guide/clickhouse
guide/migrations
guide/health
guide/scaffolding
guide/whats-not-in-v1
```

```{toctree}
:maxdepth: 2
:caption: API Reference

reference/index
```
