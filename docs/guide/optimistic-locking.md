# Optimistic locking

Optimistic locking prevents lost updates in concurrent systems without holding
a database lock for the duration of a read-modify-write cycle.  Each row
carries a version counter; when you write back, alchemiq checks that the
counter still matches what you read.  If another process already incremented
it, you receive a conflict exception instead of silently overwriting their
change.

---

## Enabling versioning

Set ``versioned = True`` in the model's inner ``Meta`` class:

```python
from alchemiq import Model
from alchemiq.types import PK

class Order(Model):
    id: PK[int]
    status: str
    total: int

    class Meta:
        versioned = True
```

Alchemiq injects a ``_version`` column (``BIGINT``, non-nullable,
``server_default`` 1 so the counter starts at 1) automatically, backed by
SQLAlchemy's native ``version_id_col`` mechanism.
The single-underscore name avoids collisions with a business-level ``version``
field you might declare yourself.

---

## Reading the current version

Use {func}`~alchemiq.version_of` to read the ``_version`` value from a fetched
instance:

```python
from alchemiq import Repository, version_of
from myapp.models import Order

orders = Repository(Order)
order  = await orders.get(id=1)
ver    = version_of(order)   # e.g. 2
```

{func}`~alchemiq.version_of` raises ``ConfigError`` if the model was not
declared with ``Meta.versioned = True``.

---

## Conditional update and delete

Pass the version you observed as ``expected_version`` (keyword-only) to
``update()`` or ``delete()``.  Alchemiq checks it before the flush:

```python
# Update - fails if the row was modified since order was fetched
await orders.update(1, expected_version=ver, status="paid")

# Delete - same guard applies
await orders.delete(1, expected_version=ver)
```

If the check fails, {class}`~alchemiq.ConcurrentModificationError` is raised
and nothing is written.  Map it to an HTTP 409 response:

```python
from alchemiq import ConcurrentModificationError
from fastapi import HTTPException

try:
    await orders.update(1, expected_version=ver, status="paid")
except ConcurrentModificationError:
    raise HTTPException(status_code=409, detail="Order was modified by another request.")
```

Even without an explicit ``expected_version``, SQLAlchemy's native
``version_id_col`` increments ``_version`` on every flush and raises
``StaleDataError`` if the counter was already bumped by a concurrent
transaction.  Alchemiq translates that into {class}`~alchemiq.ConcurrentModificationError`
as well.

---

## Bulk operations bypass the version check

``bulk_create()``, ``filter().update()``, and ``filter().delete()`` operate at
the SQL level and do **not** enforce the version counter.  Use single-row
``update()`` / ``delete()`` whenever optimistic concurrency matters.
