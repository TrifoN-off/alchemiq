# Repository

{class}`~alchemiq.Repository` is the primary data-access façade for a single
model.  Instantiate it ad-hoc with ``Repository(Model)`` or subclass
``Repository[Model]`` to attach default settings such as caching.

```python
from alchemiq import Repository
from myapp.models import User

# ad-hoc
users = Repository(User)

# subclass - can add cache, default ordering, etc.
class UserRepository(Repository[User]):
    cache = True
    cache_ttl = 300
```

All methods are `async`.

---

## CRUD operations

### Creating rows

``create(**values)`` instantiates the model, persists it, and returns the new
instance:

```python
user = await users.create(name="Ada Lovelace", email="ada@example.com")
print(user.id)  # auto-assigned PK
```

### Reading rows

``get(**lookups)`` returns exactly one row, or raises if none or many match:

```python
user = await users.get(id=1)
user = await users.get(email="ada@example.com")
# raises NotFoundError if absent, MultipleResultsFound if ambiguous
```

``get_or_none(**lookups)`` is the same but returns ``None`` instead of raising
``NotFoundError``:

```python
user = await users.get_or_none(id=99)   # None if not found
```

Positional {class}`~alchemiq.Q` expressions are accepted alongside keyword
lookups in both methods:

```python
user = await users.get(Q(role="admin"), email="alice@example.com")
```

Other read helpers:

```python
first  = await users.first()               # first row (no guaranteed order without order_by)
last   = await users.last()                # last row (reverses ordering or falls back to -PK)
all_   = await users.all()                 # list of all rows
exists = await users.exists(status="active")
count  = await users.count(status="active")
```

### Updating rows

``update(id, **changes)`` applies the changes and returns the refreshed instance:

```python
user = await users.update(3, name="Ada King")
```

For optimistic concurrency, pass ``expected_version`` (read with
``alchemiq.version_of(obj)`` on versioned models):

```python
ver = alchemiq.version_of(user)
user = await users.update(3, expected_version=ver, name="Ada King")
# raises ConcurrentModificationError if the row was changed concurrently
```

### Deleting rows

``delete(id)`` performs a soft-delete (stamps ``deleted_at``) if the model has
``Meta.soft_delete = True``, otherwise issues a physical ``DELETE``:

```python
await users.delete(3)
```

``hard_delete(id)`` always removes the physical row regardless of soft-delete
configuration.

---

## Filtering and chaining

All filter methods on {class}`~alchemiq.Repository` delegate to
{class}`~alchemiq.QuerySet` and return a `QuerySet` you can chain further:

```python
# filter -> order -> paginate
page = await (
    users
    .filter(status="active")
    .order_by("-created_at")
    .paginate(page=1, size=20)
)
```

See the [Queries guide](queries.md) for the full filter and builder API.

---

## Offset pagination

``paginate(page, size)`` issues two queries (count + windowed fetch) and returns
a {class}`~alchemiq.Page`:

```python
page = await users.filter(status="active").order_by("id").paginate(page=1, size=20)

page.items      # list[User]   - current page rows
page.total      # int          - total matching rows
page.page       # int          - current page number (1-based)
page.size       # int          - requested page size
page.pages      # int          - total number of pages
page.has_next   # bool
page.has_prev   # bool
```

:::{note}
`count()` and `all()` run in two separate database sessions.  A row inserted
between the two queries may inflate `total` without appearing in `items`, or
vice versa.
:::

---

## Cursor / keyset pagination

For high-volume lists where offset pagination becomes slow, use keyset
pagination.  ``cursor_paginate(*, size, after, before)`` (keyword-only arguments)
adds a PK tiebreaker and returns a {class}`~alchemiq.CursorPage` -
**no total-count query**:

```python
p1 = await users.order_by("created_at").cursor_paginate(size=20)

p1.items        # list[User]    - current page rows
p1.next_cursor  # str | None    - opaque token; pass as after= to fetch next page
p1.prev_cursor  # str | None    - opaque token; pass as before= to fetch previous page
p1.has_next     # bool
p1.has_prev     # bool
```

Navigate forward by passing the previous page's ``next_cursor``:

```python
p2 = await users.order_by("created_at").cursor_paginate(size=20, after=p1.next_cursor)
```

Navigate backward with ``before=``:

```python
p0 = await users.order_by("created_at").cursor_paginate(size=20, before=p1.prev_cursor)
```

``after`` and ``before`` are mutually exclusive; the cursor tokens are opaque
base64 strings encoding the effective ordering position.  Keyset pagination is
stable under concurrent inserts and O(1) at any page depth.

---

## Bulk operations

### bulk_create

``bulk_create(objs)`` inserts multiple instances in one flush:

```python
rows = await users.bulk_create([
    User(name="Alice", email="alice@example.com"),
    User(name="Bob",   email="bob@example.com"),
])
```

Fires no per-row signals and writes no outbox entries.

### bulk_upsert (PostgreSQL)

``bulk_upsert(objs)`` emits an idempotent ``INSERT ... ON CONFLICT`` statement.
Returns the number of rows affected (inserted + updated).

```python
n = await users.bulk_upsert([User(id=1, email="a@x.c", name="A")])
```

By default the conflict target is the primary key and all non-conflict columns
are updated.  Override with keyword arguments:

```python
# conflict on a unique email column; update only the name
await users.bulk_upsert(
    [User(id=1, email="dup@x.c", name="First")],
    conflict=["email"],
    update_fields=["name"],
)

# skip conflicting rows silently
await users.bulk_upsert(rows, ignore_conflicts=True)
```

``bulk_upsert`` is PostgreSQL-only.  It fires no signals and writes no outbox
entries.

### bulk_update

``bulk_update(objs, fields)`` runs a bulk `UPDATE` by PK for the listed columns
and returns the count of submitted objects:

```python
n = await users.bulk_update(rows, fields=["status", "updated_at"])
```

The returned count is ``len(items)`` - the number of objects you submitted, **not**
the database rowcount.  Rows whose PK is absent from the table are silently skipped
by SQLAlchemy's bulk path, so do not rely on this count to detect missing PKs.

---

## Aggregations

``aggregate(**exprs)`` computes reduce-aggregates over the filtered set and
returns a ``dict`` mapping each alias to its computed value.

Import the aggregate expressions from ``alchemiq``:

```python
from alchemiq import Count, Sum, Avg, Min, Max

stats = await users.filter(status="active").aggregate(
    total=Sum("balance"),
    n=Count(),
    avg_age=Avg("age"),
    min_age=Min("age"),
    max_age=Max("age"),
)
# {"total": Decimal("..."), "n": 42, "avg_age": 31.5, "min_age": 18, "max_age": 65}
```

{class}`~alchemiq.Sum`, {class}`~alchemiq.Avg`, {class}`~alchemiq.Min`, and
{class}`~alchemiq.Max` return ``None`` over an empty set; {class}`~alchemiq.Count`
returns ``0``.

``Count()`` emits ``count(*)``.  Pass a field name for ``count(col)``, or set
``distinct=True`` for ``count(DISTINCT col)``:

```python
stats = await users.aggregate(
    n=Count(),
    unique_emails=Count("email", distinct=True),
)
```

There is no ``GROUP BY`` - ``aggregate()`` always returns a single row.

---

## Explain (query plan)

``.explain()`` runs ``EXPLAIN`` on the compiled ``SELECT`` and returns the
plan.  It is a diagnostic tool only - never cached, PostgreSQL-only:

```python
# textual plan (str)
plan = await users.filter(status="active").explain()
print(plan)

# EXPLAIN ANALYZE - real execution, real timings (str)
plan = await users.filter(status="active").explain(analyze=True)

# parsed JSON plan (list)
plan = await users.filter(status="active").explain(format="json")
```

``analyze=True`` executes the underlying ``SELECT`` inside a rolled-back
read-only transaction so no data is modified.

``.explain()`` is also available directly on {class}`~alchemiq.QuerySet`.
