# ClickHouse support

alchemiq provides a first-class ClickHouse integration under the ``[clickhouse]``
extra: an annotation-first model base, three MergeTree-family engine descriptors,
a typed repository, buffered inserts, and a custom migration runner (Alembic does
not support ClickHouse).

```bash
pip install "alchemiq[clickhouse]"
```

ClickHouse and PostgreSQL have **separate** SQLAlchemy metadata and mapper
registries, so the two never interfere.

---

## Declaring a model

Subclass ``ClickHouseModel`` and set ``Meta.engine`` to one of the three
supported engine descriptors.  ``order_by`` is required - ClickHouse uses the
ORDER BY key for sorting and (in ``ReplacingMergeTree``) for deduplication:

```python
import datetime as dt
from alchemiq.clickhouse import ClickHouseModel, MergeTree, ReplacingMergeTree
from alchemiq.clickhouse.types import DateTime64, UInt32

class PageView(ClickHouseModel):
    event_time: dt.datetime = DateTime64(3)
    user_id: int = UInt32()

    class Meta:
        engine = MergeTree(order_by=("event_time", "user_id"))
```

---

## Engine descriptors

| Engine | Use case |
|---|---|
| ``MergeTree`` | General-purpose append-only analytics |
| ``ReplacingMergeTree`` | Deduplication by ORDER BY key; required for soft-delete |
| ``AggregatingMergeTree`` | Aggregate-function columns |

All three share the same keyword arguments:

| Parameter | Description |
|---|---|
| ``order_by`` | Tuple of column names or a SQL expression string (required) |
| ``partition_by`` | Optional partition expression |
| ``primary_key`` | Optional PRIMARY KEY (subset of ORDER BY) |
| ``ttl`` | Optional TTL expression, e.g. ``"event_time + INTERVAL 90 DAY"`` |
| ``sample_by`` | Optional SAMPLE BY expression |
| ``settings`` | Optional dict of ENGINE-level settings |

``ReplacingMergeTree`` also accepts ``version`` (column name for dedup version)
and ``is_deleted`` (column name for tombstone flag).

### Soft-delete models

Set ``Meta.soft_delete = True`` with ``ReplacingMergeTree``.  alchemiq injects
``is_deleted``, ``_version``, and ``deleted_at`` columns automatically:

```python
class Document(ClickHouseModel):
    key: int = UInt32()
    body: str

    class Meta:
        soft_delete = True
        engine = ReplacingMergeTree(order_by=("key",))
```

``SELECT ... FINAL`` retains the row with the highest ``_version`` and filters
out rows where ``is_deleted=1``.  Use ``repo.with_deleted()`` or
``repo.only_deleted()`` to bypass the filter.

---

## Creating and dropping tables

```python
from alchemiq.clickhouse import create_clickhouse_tables, drop_clickhouse_tables

await create_clickhouse_tables()   # CREATE TABLE IF NOT EXISTS for every model
await drop_clickhouse_tables()     # DROP TABLE IF EXISTS (reverse order)
```

---

## ClickHouseRepository

``ClickHouseRepository`` is the data-access surface for one ClickHouse model.
Instantiate it directly or subclass with a type parameter:

```python
from alchemiq.clickhouse import ClickHouseRepository

# direct
repo = ClickHouseRepository(PageView)
await repo.insert(PageView(event_time=dt.datetime.now(dt.UTC), user_id=42))

# typed subclass
class PageViewRepo(ClickHouseRepository[PageView]):
    pass

rows = await PageViewRepo().filter(user_id=42).order_by("event_time").all()
```

### Filtering

``Q`` objects work the same way as for PostgreSQL:

```python
from alchemiq import Q

rows = await repo.filter(Q(user_id__gt=100)).order_by("-event_time").limit(50).all()
```

### Insert methods

| Method | Description |
|---|---|
| ``insert(*objs)`` | Insert one or more model instances immediately |
| ``bulk_insert(objs)`` | Optimised batch insert |
| ``buffered(...)`` | Returns a ``BufferedInserter`` context manager |

### Buffered insertion

``BufferedInserter`` accumulates rows in memory and flushes to ClickHouse when
``max_rows`` is reached or every ``flush_interval`` seconds:

```python
async with repo.buffered(max_rows=1000, flush_interval=5.0) as buf:
    for event in events:
        await buf.add(event)
# all rows flushed on exit
```

### Raw SQL

``repo.raw`` executes a literal SQL string and returns results as plain dicts
(or as model instances when ``as_model=True``):

```python
rows = await repo.raw(
    "SELECT region, sum(amount) AS total FROM _sale GROUP BY region ORDER BY region"
)
# rows == [{"region": "EU", "total": 30}, ...]

instances = await repo.raw(
    "SELECT * FROM page_view WHERE user_id = {uid:UInt32}",
    params={"uid": 42},
    as_model=True,
)
```

### Soft-delete on ClickHouse

``ClickHouseRepository.delete(**lookups)`` is supported for models with
``Meta.soft_delete = True``.  It does **not** issue a SQL ``DELETE`` - instead it
appends a tombstone row (same ORDER BY key, ``is_deleted=1``); a subsequent
``SELECT ... FINAL`` collapses the key to the latest version and hides the row.
The lookups must supply every column in the ORDER BY key, or
``UnsupportedOperationError`` is raised eagerly before any IO.

```python
repo = ClickHouseRepository(Document)
await repo.insert(Document(key=1, body="hello"))
await repo.delete(key=1)    # tombstone inserted; row hidden under FINAL
await repo.restore(key=1)   # un-delete (live marker with is_deleted=0)
await repo.cleanup()        # OPTIMIZE ... FINAL CLEANUP - physically drop tombstones
```

``delete`` raises ``UnsupportedOperationError`` if the model is **not**
soft-delete (there is no physical/hard row ``DELETE`` on ClickHouse).

### Unsupported operations

ClickHouse is append-only.  The following methods raise
``UnsupportedOperationError``:

- ``update(...)`` and ``bulk_update(...)`` - ClickHouse has no row UPDATE
- ``get_or_create(...)`` and ``update_or_create(...)`` - ClickHouse has no upsert; use ``insert`` / ``bulk_insert``

---

## Outbox integration

``ClickHousePublisher`` is a ``Publisher`` adapter that writes outbox messages
directly into a ClickHouse table in batches.  Wire it into a ``Relay`` the same
way as any other publisher:

```python
from alchemiq import Relay
from alchemiq.clickhouse import ClickHousePublisher

relay = Relay(ClickHousePublisher(EventRepo), batch_size=500)
await relay.run()
```

---

## Migrations

alchemiq ships its own migration runner for ClickHouse (Alembic does not support
it).  Migrations are Python classes with ``up`` and ``down`` methods.  Applied
revisions are stored in a ``_alchemiq_migrations`` MergeTree table in ClickHouse
itself.

### CLI commands

```bash
alchemiq makemigrations --db clickhouse
alchemiq migrate --db clickhouse
alchemiq rollback --db clickhouse
alchemiq history --db clickhouse    # list migrations with applied markers
alchemiq showsql --db clickhouse    # print DDL for pending migrations (reads history, runs nothing)
```

``alchemiq history`` reads the ``_alchemiq_migrations`` table and prints each
revision with a ``[x]`` (applied) or ``[ ]`` (pending) marker.

``alchemiq showsql`` connects to ClickHouse to read the applied-revision history
and prints the DDL SQL for pending migrations without executing it.

---

## PostgreSQL-only features

The following alchemiq features are **not available** for ClickHouse:

| Feature | Reason |
|---|---|
| ``UnitOfWork`` / transactions | ClickHouse has no ACID transactions |
| Optimistic locking (``Meta.versioned``) | Requires row-level UPDATE |
| Physical/hard row ``DELETE`` | Append-only storage (soft-delete via tombstone is supported) |
| ``QuerySet.explain()`` (PostgreSQL EXPLAIN) | PG-specific; use CH ``EXPLAIN`` syntax via ``repo.raw`` |
| Alembic migrations | Alembic has no ClickHouse dialect |
| Native upsert | ClickHouse has no upsert; use ``insert`` / ``bulk_insert`` |
| Model signals on write | No ORM-level flush |
