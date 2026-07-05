# Getting started

## Installation

Install the core library plus all optional integrations in one shot:

```bash
pip install "alchemiq[all]"
```

Or pick only what your project needs.  The core package ships no database
driver, so for PostgreSQL start from the `postgres` extra - it installs the
`asyncpg` driver used by every `postgresql+asyncpg://` DSN in this guide:

```bash
pip install "alchemiq[postgres]"
```

| Extra | What it adds |
|---|---|
| `email` | `Email` field validation (`email-validator`) |
| `phone` | `Phone` field validation (`phonenumbers`) |
| `argon2` | Argon2 password hashing (`argon2-cffi`) |
| `bcrypt` | bcrypt password hashing (`bcrypt`) - not included in `all` |
| `crypto` | `Encrypted` field transparent encryption (`cryptography`) |
| `outbox` | Outbox/Relay worker via TaskIQ + aio-pika (`taskiq`, `taskiq-aio-pika`) |
| `fastapi` | FastAPI CRUD router + dependency injection (`fastapi`) |
| `faststream` | FastStream publisher + consumer DI (`faststream`) |
| `redis` | Repository-level Redis caching (`redis`) |
| `postgres` | Async PostgreSQL driver (`asyncpg`) |
| `clickhouse` | ClickHouse models + repository (`clickhouse-connect[async]`, `clickhouse-sqlalchemy`) |
| `migrations` | Alembic-based migration CLI (`alembic`) |

## Minimal end-to-end example

The steps below get a working database-backed service running from scratch.

1. **Define a model.** Subclass {class}`~alchemiq.Model` and declare fields using plain Python type annotations:

   ```python
   import alchemiq
   from alchemiq import Model
   from alchemiq.types import PK, Email

   class User(Model):
       id: PK[int]
       name: str
       email: Email
   ```

2. **Configure the engine.** Call {func}`~alchemiq.configure` once at startup with an async-compatible DSN:

   ```python
   alchemiq.configure("postgresql+asyncpg://user:password@localhost/mydb")
   ```

3. **Create tables.** Call `create_all()` to emit `CREATE TABLE IF NOT EXISTS` for every mapped model:

   ```python
   await alchemiq.create_all()
   ```

4. **Use a Repository.** Instantiate {class}`~alchemiq.Repository` with your model class to get a full CRUD surface:

   ```python
   from alchemiq import Repository

   users = Repository(User)

   # create a row
   user = await users.create(name="Ada Lovelace", email="ada@example.com")

   # fetch by primary key
   found = await users.get(id=user.id)
   print(found.name)  # Ada Lovelace
   ```

That is the complete setup. All queries are `async`/`await`; no synchronous mode is provided.
