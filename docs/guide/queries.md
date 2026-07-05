# Queries: Q and QuerySet

Alchemiq provides two composable layers for building database queries:
{class}`~alchemiq.Q` - a predicate tree for filtering - and
{class}`~alchemiq.QuerySet` - an immutable lazy builder that compiles to a
SQLAlchemy `SELECT`.

---

## Q objects

A {class}`~alchemiq.Q` object is a single filter condition expressed as
``field__operator=value`` keyword arguments:

```python
from alchemiq import Q

q = Q(status="active")          # status = 'active'  (implicit __eq)
q = Q(age__gte=18)              # age >= 18
q = Q(role__in=["admin", "staff"])  # role IN ('admin', 'staff')
```

### Supported lookup operators

| Suffix | SQL equivalent |
|---|---|
| *(none)* or `__eq` | `= value` |
| `__ne` | `!= value` |
| `__lt` | `< value` |
| `__lte` | `<= value` |
| `__gt` | `> value` |
| `__gte` | `>= value` |
| `__in` | `IN (...)` |
| `__not_in` | `NOT IN (...)` |
| `__isnull` | `IS NULL` / `IS NOT NULL` |
| `__contains` | `LIKE '%value%'` |
| `__icontains` | `ILIKE '%value%'` |
| `__startswith` | `LIKE 'value%'` |
| `__endswith` | `LIKE '%value'` |

### Combining predicates

Combine {class}`~alchemiq.Q` objects with Python's bitwise operators:

```python
# AND - both conditions must hold
active_adults = Q(status="active") & Q(age__gte=18)

# OR - at least one must hold
admins_or_staff = Q(role="admin") | Q(role="staff")

# NOT - negate a condition
not_deleted = ~Q(deleted=True)
```

Operators nest to arbitrary depth, giving you full boolean algebra:

```python
q = (Q(role="admin") | Q(role="staff")) & ~Q(banned=True)
```

### Passing Q to filter/get

Pass a composed {class}`~alchemiq.Q` to any ``filter()`` or ``get()`` call:

```python
from alchemiq import Repository, Q
from myapp.models import User

users = Repository(User)

active = await users.filter(Q(status="active") & Q(age__gte=18)).all()
admin = await users.get(Q(role="admin"), email="alice@example.com")
```

---

## QuerySet

A {class}`~alchemiq.QuerySet` is a lazy, immutable query builder.
Every builder method returns a **new** `QuerySet`; the original is unchanged.
No I/O happens until you call a terminal method.

### Building a query

```python
from alchemiq import QuerySet
from myapp.models import Order

# filter, order, and limit are all lazy - no query yet
qs = (
    QuerySet(Order)
    .filter(Q(status="paid") & Q(total__gte=100))
    .order_by("-created_at")
    .limit(50)
)
```

**Builder methods:**

| Method | What it does |
|---|---|
| `.filter(*Q, **lookups)` | Narrow results (AND) |
| `.exclude(*Q, **lookups)` | Exclude matching rows (NOT AND) |
| `.order_by(*fields)` | Set `ORDER BY`; prefix `-` for descending |
| `.limit(n)` | Apply `LIMIT n` |
| `.offset(n)` | Apply `OFFSET n` |
| `.distinct()` | Emit `SELECT DISTINCT` |
| `.only(*fields)` | Project to named columns |
| `.select_related(*names)` | JOIN-load relationships (joinedload) |
| `.prefetch_related(*names)` | SELECT-IN-load relationships (selectinload) |

Slicing also works: ``qs[10:30]`` is equivalent to ``.offset(10).limit(20)``.

### Terminal methods

Terminals execute the query and return results:

| Terminal | Returns |
|---|---|
| `.all()` | `list[Model]` |
| `.first()` | `Model \| None` (`LIMIT 1`) |
| `.last()` | `Model \| None` (reversed ordering) |
| `.get(**lookups)` | `Model` or raises `NotFoundError` / `MultipleResultsFound` |
| `.get_or_none(**lookups)` | `Model \| None` |
| `.count()` | `int` |
| `.exists()` | `bool` |
| `.aggregate(**exprs)` | `dict[str, Any]` |
| `.paginate(page, size)` | `Page[Model]` |
| `.cursor_paginate(*, size=20, after=..., before=...)` | `CursorPage[Model]` |
| `.explain(*, analyze=False, format="text")` | `str \| list` |

All terminals are `async`:

```python
orders = await QuerySet(Order).filter(status="paid").order_by("-created_at").all()
first_order = await QuerySet(Order).order_by("created_at").first()
count = await QuerySet(Order).filter(status="pending").count()
```

---

## Set-based write operations and the full-table guard

{class}`~alchemiq.QuerySet` exposes `.update()` and `.delete()` for bulk writes.
Both **require at least one filter** to guard against accidental full-table mutations:

```python
# raises QueryError - no filter set
await QuerySet(Order).update(status="archived")

# correct: filter first
n = await QuerySet(Order).filter(status="pending").update(status="archived")
```

When you genuinely need to touch every row, use the explicit escape-hatch methods
`.update_all()` and `.delete_all()`, which carry no filter requirement:

```python
# full-table update - intentional, lexically distinct call
await QuerySet(Order).update_all(status="archived")

# full-table delete
await QuerySet(Order).delete_all()
```

The same guard and escape hatches are available on {class}`~alchemiq.Repository`
directly: ``repo.filter(...).update(...)`` vs ``repo.update_all(...)``.

---

## Q serialization for RPC

In a microservice architecture you may need to pass a filter from one service to
another - over a message queue, HTTP, or a query parameter.
{class}`~alchemiq.Q` is fully serializable:

```python
q = Q(status="active") & Q(age__gte=18)

# serialize
payload = q.to_data()       # compact JSON-safe nested list
raw     = q.to_bytes()      # compact UTF-8 JSON bytes
token   = q.to_base64()     # urlsafe base64 string (safe for query params)
```

Reconstruct on the receiving side - always validating fields against the model:

```python
q = Q.from_data(payload, User)
q = Q.from_bytes(raw, User)
q = Q.from_base64(token, User)
```

### Allow-list and deny-list

Deserialization validates every field path against the model.
By default, relationship traversal (``user__role``) is **denied**.
Use ``allow`` to opt individual paths in, and ``deny`` to block specific fields:

```python
q = Q.from_data(
    payload,
    User,
    allow={"status", "age"},          # only these fields accepted
    deny={"password_hash"},           # also block this one explicitly
)
```

``from_bytes`` and ``from_base64`` accept the same ``allow`` / ``deny`` keyword
arguments.

**Exceptions raised on invalid payloads:**

- ``DeserializationError`` - malformed payload structure or invalid JSON.
- ``DisallowedFieldError`` - field not in allow-list, in deny-list, or unknown on the model.
- ``UnknownOperatorError`` - unrecognised lookup suffix in the payload.
