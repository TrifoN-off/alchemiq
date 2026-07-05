# What's not in v1

alchemiq v0.1.0 is a public beta with a deliberately focused scope.  The items
below are not present because they were deferred in favour of shipping a solid,
well-tested core.  They are on the roadmap and will be addressed in future
releases - none of them are bugs, and none of them were forgotten.

---

## Query and ORM layer

- **Streaming results** - ``QuerySet.stream(batch_size=)`` for memory-efficient
  iteration over large result sets.
- **Nested relation loading** - multi-hop ``select_related`` and
  ``prefetch_related`` (e.g. ``author__company``).  v1 supports one hop only.
- **Multi-hop self-referential joins** - ``parent__parent__name`` and cases
  where two foreign keys point at the same table require per-hop aliasing.
- **`.values()` / `.values_list()`** - flat projection methods.
- **`F()` expressions** - column-reference objects for in-database arithmetic.
- **`DISTINCT ON (...)`** - PostgreSQL-specific distinct-on filtering.
- **Raw-SQL escape hatch at the repository level** - calling arbitrary SQL
  strings through a repository method.
- **Synchronous mode** - alchemiq is async-only; there is no ``sync`` engine.
- **Multiple simultaneous databases** - connecting to more than one PostgreSQL
  instance in the same application.
- **Full `.annotate()`** - computed columns and aggregate annotations on
  QuerySets.  v1 provides ``repo.aggregate(Count / Sum / Avg / Min / Max)``
  over a whole queryset; per-row annotation is post-v1.

---

## ClickHouse

- **Generic row UPDATE** - ClickHouse does not support ``UPDATE`` in the
  standard sense; a first-class ``update`` via ``ReplacingMergeTree`` is
  planned.
- **Additional exotic types** - ``Array``, ``Map``, ``Nested``, ``Tuple``,
  ``AggregateFunction``, ``FixedString``, ``Enum16`` are not yet covered by the
  type system; ``LowCardinality`` composition/nesting is deferred (the base
  ``LowCardinality`` type itself is supported).
- **Additional engines** - ``CollapsingMergeTree``,
  ``VersionedCollapsingMergeTree``, distributed and replicated variants.
- **Lightweight DELETE / mutations** - ``ALTER TABLE ... DELETE`` mutations are
  not exposed through the migration runner.
- **Server-side query parameters** - v1 uses ``literal_binds=True`` for
  ClickHouse queries; moving to server-side parameters is a hardening item.

---

## Signals and serialization

- **After-commit signals** - ``on_commit`` callbacks that fire only after the
  database transaction commits successfully.
- **Signal handler inheritance** - MRO-based resolution of handlers defined on
  parent model classes.
- **Soft-delete cascade** - automatically propagating a soft-delete to related
  rows.
- **Partial unique indexes for soft-delete** - the unique-slot problem (a
  deleted row holding a value that a new row should be able to claim) is not
  solved in v1.
- **Changed-fields payload** - ``post_update`` signals do not yet carry a diff
  of which fields changed.
- **Bring-your-own Pydantic schema for `to_pydantic`** - passing a custom
  schema class to override the auto-derived one.
- **Nested and validator-ported Pydantic schemas** - ``to_pydantic`` derives a
  flat schema; nested related models and ported field validators are post-v1.
- **Mass `QuerySet.restore()`** - restoring soft-deleted rows in bulk via a
  queryset; v1 restores one row at a time.

---

## Outbox and relay

- **Strict per-aggregate ordering** - the relay worker processes messages in
  FIFO order per outbox table, but per-aggregate strict ordering within a shared
  table is post-v1.
- **Per-event exponential back-off** - retries use a fixed interval; a
  ``next_retry_at`` column for exponential back-off is planned.
- **Relay CLI sub-command** - ``alchemiq relay`` to start the relay worker from
  the command line.
- **Dead-letter tooling** - operator commands to inspect and replay ``dead``
  outbox rows.
- **Real RabbitMQ integration tests in CI** - the CI suite mocks the broker;
  a live RabbitMQ container test is planned once CI infra exists.
- **Per-model topic override** - specifying a custom topic name per model class.
- **Changed-field diff payloads in events** - emitting only changed fields in
  update events.
- **Outbox events for bulk and mass operations** - ``bulk_create``,
  ``mass_update``, and ``mass_delete`` do not emit outbox events in v1.
- **Broker-side batch publish for the TaskIQ path** - the non-ClickHouse
  (TaskIQ) relay publishes one message per call; batched broker-side publishing
  is planned.

---

## FastAPI integration

- **Class-based CRUDRouter subclassing** - overriding individual endpoints by
  subclassing the router rather than replacing it.
- **Per-endpoint dependency injection** - injecting dependencies at the
  individual endpoint level rather than the router level.
- **Restore / hard-delete / bulk endpoints** - the auto-generated router covers
  the five standard operations; restore, hard-delete, and bulk variants are
  post-v1.
- **Embedding loaded relations in responses** - returning nested related objects
  in the same response.
- **ETag-based response caching** - HTTP-level caching with conditional
  ``GET``.
- **Configurable success status codes and response envelopes.**
- **OpenAPI example enrichment.**
- **Rate limiting.**

---

## Migrations

- **Alembic branching and multi-head merge** - v1 enforces a linear migration
  history.
- **Multi-step rollback** - ``rollback`` undoes exactly one migration; rolling
  back to an arbitrary revision is post-v1.
- **ClickHouse autogenerate for destructive operations** - dropping columns,
  changing a column type, or switching a table engine must be written by hand.
- **ClickHouse autogenerate of ORDER BY / PARTITION BY changes** - v1 compares
  the engine name only; detecting sorting-key or partition-key changes is
  post-v1.
- **`showsql` for an arbitrary revision range** - v1 prints the SQL for pending
  migrations only; selecting an arbitrary revision range is planned.
- **Concurrent-migration locking** - no advisory lock prevents two processes
  from running migrations at the same time.
- **Data-migration helpers** - v1 provides ``op.execute`` for raw SQL; a
  higher-level data-migration API is planned.
- **Zero-downtime / online-schema migration orchestration** - ``CREATE INDEX
  CONCURRENTLY`` and ``ALTER TABLE ... ADD COLUMN ... DEFAULT`` patterns are not
  orchestrated by the runner in v1.
- **`stamp`, `merge`, and `squash`** - Alembic sub-commands beyond the five
  documented CLI commands are not exposed.

---

## Caching

- **Negative caching** - caching ``None`` / ``NotFound`` results to prevent
  cache-penetration attacks.
- **Stampede / dogpile protection** - a single-flight lock on cache miss.
- **Pluggable serializers** - v1 uses JSON only; msgpack and pickle variants are
  planned.
- **Fine-grained per-aggregate invalidation** - tracking which cache keys
  belong to an aggregate so they can be flushed without a ``SCAN``.

---

## Health checks

- **Strict-readiness toggle** - when no backend is configured, ``check_health``
  currently reports the service as healthy.  An opt-in
  "no backend configured ⇒ unhealthy" mode is post-v1.
- **Per-component timeouts and a component selector** - v1 applies a single
  timeout to every probe; per-component timeouts and a ``components=[...]``
  selector to probe a subset are planned.
