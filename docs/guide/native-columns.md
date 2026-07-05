# Native SQLAlchemy columns (escape hatch)

Alchemiq covers the most common column types out of the box.
When you need something it does not model natively - JSONB, custom `TypeDecorator`s,
computed columns, exotic PK types - declare the column using standard SQLAlchemy 2.0
syntax and alchemiq will integrate it transparently.

---

## Declaring a native column

Use `Mapped[...]` with `mapped_column(...)` exactly as you would in plain SQLAlchemy:

```python
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

class Document(Model):
    id: PK[int]
    payload: Mapped[dict | None] = mapped_column(JSONB)
```

Alchemiq detects the `Mapped[...] = mapped_column(...)` signature and registers the
column in `__alchemiq_fields__` as a passthrough (`_NativeField`).
SQLAlchemy owns the column definition; alchemiq does not rewrite the annotation or
call its own `build_column` pipeline for it.

---

## First-class integration

A native column registered in `__alchemiq_fields__` participates in the full
alchemiq query and serialization stack:

- **Filtering:** `repo.filter(payload__contains={"key": "value"})` - the field name
  resolves through `__alchemiq_fields__` the same way typed fields do.
- **Ordering:** `repo.order_by("payload")` works as expected.
- **Serialization:** `doc.to_dict()` and `doc.to_pydantic()` include the native
  column in their output by default.
- **Schema exposure:** `Document.to_schema()` returns a Pydantic class that
  exposes the native column as a field, with the Python type inferred from
  `Mapped[dict | None]`.
- **Primary key discovery:** a native column declared with `primary_key=True` is
  recognised as the model's PK for repository operations and FK referencing.

---

## No eager validation

Native columns carry **no eager validation**.
The `validate()` hook that fires on every field assignment for typed alchemiq fields
is not wired for native columns - that is the point of the escape hatch.
Correctness of the value is your responsibility.

---

## Config reconciliation

After SQLAlchemy maps the model (`super().__init_subclass__()` completes), alchemiq
runs `reconcile_native_fields` to read the actual `nullable`, `unique`, `index`, and
`primary_key` flags from the mapped `Column` on `cls.__table__` and fills
`_NativeField.config` from those authoritative values.
This means `__alchemiq_fields__` always reflects the real database column attributes,
even though alchemiq did not build the column itself.

---

(native-relationship-escape-hatch)=
## Native `relationship()` escape hatch

To declare a relationship that the alchemiq sugar does not support - a through-model
M2M with extra columns, a self-referential M2M, or any fully custom join - use a
native SQLAlchemy `relationship()`:

```python
from sqlalchemy.orm import Mapped, relationship

post_tag = ...  # a SQLAlchemy Table object for the through-model

class Post(Model):
    id: PK[int]
    tags: Mapped[list[Tag]] = relationship(secondary=post_tag, lazy="raise_on_sql")
```

When alchemiq's pipeline processes `Post`, it detects the `relationship()` value via
the `NATIVE_RELATIONSHIP` sentinel and **skips** it in `prepare_fields` - the column
is not added to `__alchemiq_fields__` and no eager validation is wired.
SQLAlchemy maps the relationship normally.

Registration is reactive, driven by an unloaded-relationship access.
When you read a relationship attribute that was not loaded, SQLAlchemy raises
`InvalidRequestError` / `DetachedInstanceError`; the model's `__getattribute__`
catches that error and lazily calls `register_native_relationships`, which runs
`configure_mappers()` and reads the resolved direction and target from the SQLAlchemy
inspector, entering the relationship into `__alchemiq_relationships__`.
The call is idempotent - it runs at most once per class.
If the relationship was eager-loaded (via `select_related` / `prefetch_related`),
no error is raised and this path is never taken; alchemiq's own sugar relationships
are registered eagerly at class-definition time and are skipped here.
Once registered, the relationship works with `select_related` and `prefetch_related`
by name.

**ClickHouse models** are unaffected - `register_native_relationships` is a no-op for
`ClickHouseModel` because it has no `__alchemiq_relationships__` registry.

:::{note}
Alchemiq respects whatever `lazy=` strategy you declare.
Without `lazy="raise_on_sql"`, accessing the relationship on an unloaded instance
will trigger implicit SQL - the typed `RelationNotLoaded` exception is not raised.
:::
