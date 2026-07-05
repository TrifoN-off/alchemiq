# Signals and hooks

Alchemiq fires async lifecycle signals before and after each single-row
create, update, and delete operation.  You attach handlers with decorator
syntax; handlers run inside the same database transaction that triggered
the event, so a raised exception rolls the write back.

---

## The six lifecycle hooks

All hooks live in ``alchemiq.signals``.  The names follow a strict
``pre_``/``post_`` × ``create``/``update``/``delete`` scheme:

| Decorator | Fires |
|---|---|
| ``pre_create`` | Before the ``INSERT`` flush |
| ``post_create`` | After the ``INSERT`` flush (``instance.id`` is assigned) |
| ``pre_update`` | Before the ``UPDATE`` flush |
| ``post_update`` | After the ``UPDATE`` flush |
| ``pre_delete`` | Before the ``DELETE`` flush (or ``deleted_at`` stamp) |
| ``post_delete`` | After the ``DELETE`` flush (or ``deleted_at`` stamp) |

---

## Registering a handler with a decorator

Each decorator accepts an optional model class (the *sender*).  Passing a
model class registers a **per-model** handler; calling the decorator without
an argument (or passing ``None``) registers a **global** handler that fires
for every model.

### Per-model handler

```python
from alchemiq.signals import post_create
from myapp.models import User

@post_create(User)
async def on_user_created(instance, **kw):
    # instance.id is set; the INSERT has already flushed
    print(f"New user: {instance.id}")
```

### Global handler (all models)

```python
from alchemiq.signals import pre_delete

@pre_delete()
async def audit_deletion(instance, **kw):
    # fires for every model before any soft or hard delete
    print(f"Deleting {type(instance).__name__} id={instance.id}")
```

Handler callables must be **async** functions.  They receive the model
instance as the first positional argument; ``**kw`` is reserved for future
forward-compatible keyword arguments and should always be accepted.

---

## Dispatch order

For a given event, exact-sender handlers run first (in registration order),
then global handlers (in registration order).

---

## Bulk operations do not fire signals

``bulk_create()``, ``filter().update()``, and ``filter().delete()`` operate at
the SQL level and bypass the signal machinery.  Only single-row
{class}`~alchemiq.Repository` operations - ``create()``, ``update()``,
``delete()``, ``restore()``, and ``hard_delete()`` - fire signals.

---

## Imperative registration and cleanup

Use ``connect`` / ``disconnect`` when you cannot use the decorator form, and
``clear`` in test teardown:

```python
from alchemiq.signals import connect, disconnect, clear
from myapp.models import Order

async def on_order_created(instance, **kw):
    ...

# Register
connect(on_order_created, sender=Order, event="post_create")

# Remove a specific handler
disconnect(on_order_created, sender=Order, event="post_create")

# Drop all handlers (useful in test fixtures)
clear()
```
