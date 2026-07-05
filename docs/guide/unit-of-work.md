# Unit of Work

{class}`~alchemiq.UnitOfWork` wraps one database transaction.  Open it as an
`async with` context manager: the transaction commits automatically on clean
exit and rolls back if an exception propagates out.

```python
from alchemiq import UnitOfWork, Repository
from myapp.models import Order, Payment

orders   = Repository(Order)
payments = Repository(Payment)

async with UnitOfWork() as uow:
    order   = await orders.create(total=99_00, status="pending")
    payment = await payments.create(order_id=order.id, amount=99_00)
# both rows committed atomically here
```

---

## Commit and rollback

By default the transaction is managed automatically:

- **Clean exit** - the block finishes without raising -> commit.
- **Exception** - an exception propagates out of the block -> rollback, then the
  exception is re-raised.

You can also commit or roll back manually from inside the block:

```python
async with UnitOfWork() as uow:
    order = await orders.create(total=50_00, status="pending")
    await uow.commit()      # flush + commit mid-block
    # subsequent operations start a new transaction in the same session
```

```python
async with UnitOfWork() as uow:
    await orders.create(total=50_00, status="pending")
    await uow.rollback()    # abort and clear pending changes
```

:::{note}
``commit()`` and ``rollback()`` may only be called on the **outermost**
`UnitOfWork`.  Calling them on a nested (joined) instance raises
``RuntimeError`` - see the *Nested UnitOfWork* section below.
:::

---

## Repositories within a UnitOfWork

Any {class}`~alchemiq.Repository` or {class}`~alchemiq.QuerySet` call made
inside an active ``UnitOfWork`` block automatically uses the same underlying
session.  This ensures all operations in the block are part of the same atomic
transaction without any extra wiring:

```python
async with UnitOfWork() as uow:
    user  = await Repository(User).create(name="Alice", email="alice@example.com")
    audit = await Repository(AuditLog).create(action="user.created", target_id=user.id)
    # user + audit_log row committed together
```

---

## Nested UnitOfWork - reentrancy

``UnitOfWork`` is reentrant.  A nested ``async with UnitOfWork()`` block joins
the already-active session - its `__aexit__` is a no-op.  Only the outermost
block commits and closes the session:

```python
async with UnitOfWork() as outer:
    order = await orders.create(total=100_00, status="new")

    async with UnitOfWork() as inner:
        # inner.session is outer.session - same transaction
        await payments.create(order_id=order.id, amount=100_00)
        # inner exits: no commit, no close

# outer exits: single commit covers both rows
```

This makes it safe to call service functions that open their own ``UnitOfWork``
from within an outer transaction - the inner one silently joins rather than
starting a competing transaction.

---

## Savepoints

For partial rollback within a single transaction use ``uow.savepoint()``.
An exception inside the savepoint block rolls back only to that savepoint,
leaving changes made before it intact:

```python
async with UnitOfWork() as uow:
    good = await orders.create(total=50_00, status="confirmed")
    await uow.session.flush()         # make id available

    try:
        async with uow.savepoint():
            bad = await orders.create(total=-1, status="invalid")
            raise ValueError("bad order")   # rolls back to savepoint only
    except ValueError:
        pass  # good order is still pending

# only the good order is committed
```

---

## FastAPI integration

In FastAPI applications the {class}`~alchemiq.UnitOfWork` can be injected as a
dependency so you never open or close it manually in route handlers.  See the
[FastAPI integration guide](fastapi.md) for the dependency setup.
