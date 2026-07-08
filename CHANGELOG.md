# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Note:** Release entries below the marker are managed automatically by
> [Python Semantic Release](https://python-semantic-release.readthedocs.io/) -
> do not edit them by hand.

<!-- PSR inserts new releases above this line -->

## v0.2.0 (2026-07-08)

### Bug Fixes

- Track imports for nested column types in migration autogen
  ([`19c51b7`](https://github.com/TrifoN-off/alchemiq/commit/19c51b72ee91378c71c1cd5b23edd06c1a8b07d9))

JSONB astext_type and ARRAY item_type rendered as bare Text()/Integer() with no import, so the first
  migrate of any JSON/Array column raised NameError. Imports are now registered via
  autogen_context.imports, including through Maybe[...] wrappers. No DDL change.

### Documentation

- Fixed readthedocs link
  ([`a1a4c5e`](https://github.com/TrifoN-off/alchemiq/commit/a1a4c5ed6c1dbe685cb9e1f5a415535f292b757a))

- Merge hand-written 0.1.0 notes into the release changelog entry
  ([`4f2abb0`](https://github.com/TrifoN-off/alchemiq/commit/4f2abb0608c9d986ccbc6a3c47e5ae9ed2ba62bb))

### Features

- Add SQLite support (dev/test tier)
  ([`905f69f`](https://github.com/TrifoN-off/alchemiq/commit/905f69f42201bf98bbc547dddfcc26328f6a0541))

New [sqlite] extra (aiosqlite): SQLite is now a supported dialect for development, tests, and
  embedded use. Column types gain SQLite variants (UUID -> CHAR(32), JSONB -> JSON, aware datetimes,
  INTEGER pk), bulk_upsert dispatches to the SQLite ON CONFLICT insert, migrations accept a dsn key
  and use Alembic batch mode, and PG-only features (Array, .explain, multi-worker relay) refuse
  loudly. PostgreSQL stays the production target; see docs/guide/sqlite.md for the feature matrix.


## v0.1.0 (2026-07-05)

Initial public release
([`d088fb1`](https://github.com/TrifoN-off/alchemiq/commit/d088fb162f8fb127416330a3644c01856beb1fc3)).

### Added

- **Models & field types** - declarative `Model` base with annotation-first field
  types: `Email`, `Phone`, `Password`, `Encrypted`, `Money`, `Slug`, `URL`,
  `UUID4`, `UUID7`, `NanoID`, `Bounded`, `Positive`, `NonNegative`, `Percent`,
  `RoundedDecimal`, `JSON`, `Array`, `Enum`, `Maybe[T]`, `PK`, `Field`,
  `FieldType` (custom field protocol), `CreatedAt`, `UpdatedAt`, `DateTimeTz`,
  `Date`, `Time`, `UnixTimestamp`.
- **Native-column interop** - `Mapped[T] = mapped_column(...)` passthrough
  registered in `__alchemiq_fields__` with post-mapping reconciliation;
  first-class filter / serialize / FastAPI-schema / primary-key support
  including custom PKs.
- **Relationships** - `ForeignKey[Model]`, `OneToOne[Model]`, `ManyToMany[Model]`
  sugar (auto join-table generation); native `relationship()` escape-hatch via
  `NATIVE_RELATIONSHIP` sentinel.
- **Q objects & QuerySet** - chainable `Q` expressions for complex `AND`/`OR`
  filters; `QuerySet` with `.filter()`, `.exclude()`, `.order_by()`,
  `.distinct()`, `.only()` (column projection), `.select_related()`,
  `.prefetch_related()`, `.limit()`, `.offset()`, `.count()`, `.exists()`,
  `.aggregate()`, `.explain(analyze=, format=)`.
- **Repository** - async `Repository[Model]` with `get`, `filter`, `create`,
  `update`, `delete`, `bulk_create`, `bulk_upsert` (PostgreSQL `ON CONFLICT`),
  `aggregate` (`Count`, `Sum`, `Avg`, `Min`, `Max`), cursor/keyset pagination
  (`cursor_paginate`, returns `CursorPage`), offset pagination (returns `Page`),
  and `.explain()` passthrough; repo-level `cache=`/`cache_clear`/`cache_evict`.
- **Unit of Work** - `async with UnitOfWork() as uow` coordinating session,
  transaction, `commit()`, `rollback()`, and repository access.
- **Soft delete** - `Meta.soft_delete = True` adds `deleted_at`; `restore()`,
  `hard_delete()`; automatic exclusion from queries, relationship loads, and
  traversal joins; `with_deleted()` / `only_deleted()` escapes.
- **Signals** - `pre_create`, `post_create`, `pre_update`, `post_update`,
  `pre_delete`, `post_delete` lifecycle decorators; imperative `connect` /
  `disconnect`; async dispatch.
- **Optimistic locking** - `Meta.versioned = True` adds `_version` column;
  keyword-only `expected_version` on `update`/`delete`; raises
  `ConcurrentModificationError` (-> HTTP 409); `version_of(obj)` accessor.
- **Serialization** - `to_dict()` serializes a model instance to a plain dict;
  `to_schema()` returns a Pydantic class mirroring the model's columns;
  `to_pydantic()` converts an instance to a validated schema DTO;
  `Maybe[T]` partial-update sentinel with `Some`/`Nothing` unwrapping.
- **Configurable password hashing** - `Password` field ships with scrypt by
  default (Python stdlib, no extra); `configure_password_hashing("argon2" | "bcrypt")`
  switches the global scheme at startup (`[argon2]` / `[bcrypt]` extras);
  `check_password` dispatches on the stored hash's algorithm prefix
  for seamless multi-scheme migration without bulk re-hashing.
- **FastAPI integration** - `crud_router()` generating standard REST endpoints;
  provider DI; health-check router; `install_exception_handlers`.
- **Outbox & relay** - transactional outbox pattern with `OutboxMessage`,
  `OutboxEvent`, `Relay` background worker, `Publisher`/`publish`,
  `PublishError`, `TransientPublishError`; at-least-once delivery.
- **FastStream publishing** - broker-agnostic `FastStreamPublisher` adapter;
  consumer dependency injection; lifespan integration.
- **Caching** - `CacheBackend` / `InMemoryCache` / `configure_cache` /
  `reset_cache`; repository-level `cache=` parameter, `cache_clear`, `cache_evict`.
- **ClickHouse support** - `ClickHouseModel` base; `ClickHouseRepository`;
  async engine bootstrap; read-path `.explain()`; `LowCardinality` and other
  CH-native field types.
- **Migrations & unified CLI** - Alembic-backed `alchemiq` sub-commands
  (`makemigrations`, `migrate`, `rollback`, `history`, `showsql`);
  `alchemiq` top-level dispatcher.
- **`alchemiq init` scaffolding** - guided skeleton generator (stdlib-only,
  no extra deps) for single-app and monorepo layouts via `.tmpl` templates.
- **Health checks** - `check_health()` returning `HealthReport` /
  `ComponentHealth`.
