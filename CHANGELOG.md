# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Note:** From this point forward, changelog entries are managed automatically
> by [Python Semantic Release](https://python-semantic-release.readthedocs.io/).
> Do not edit entries below the `[Unreleased]` section manually.

<!-- PSR inserts new releases above this line -->

## v0.1.0 (2026-07-05)

### Features

- Initial public release
  ([`d088fb1`](https://github.com/TrifoN-off/alchemiq/commit/d088fb162f8fb127416330a3644c01856beb1fc3))


## [0.1.0] - 2026-06-29

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

[0.1.0]: https://github.com/TrifoN-off/alchemiq/releases/tag/v0.1.0
