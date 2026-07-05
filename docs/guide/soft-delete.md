# Soft delete

When a model opts in to soft deletion, calling ``delete()`` never removes the
physical row.  Instead, alchemiq stamps a ``deleted_at`` timestamp on the row
and all subsequent queries silently skip it.  Callers work with "live" data by
default; tombstoned rows are always there when you need them.

---

## Enabling soft delete

Set ``soft_delete = True`` in the model's inner ``Meta`` class:

```python
from alchemiq import Model
from alchemiq.types import PK

class Article(Model):
    id: PK[int]
    title: str

    class Meta:
        soft_delete = True
```

Alchemiq injects a ``deleted_at`` column (``TIMESTAMP WITH TIME ZONE``,
nullable) automatically.  You do not declare it yourself.

---

## Default behaviour - deleted rows are excluded

Every query on a soft-delete model applies ``WHERE deleted_at IS NULL``
transparently.  No filter code is needed:

```python
from alchemiq import Repository
from myapp.models import Article

articles = Repository(Article)

# Only live (non-deleted) articles are returned - no extra filter needed.
live = await articles.filter().all()
one  = await articles.get(id=42)
```

---

## Deleting a row

```python
await articles.delete(42)
# The row still exists in the database; deleted_at is now set.
```

Signals ``pre_delete`` / ``post_delete`` fire normally.

---

## Querying tombstoned rows

Two chainable methods control which rows are visible.

### Include deleted rows alongside live ones

```python
all_articles = await articles.filter().with_deleted().all()
```

### Show only deleted rows

```python
tombstones = await articles.filter().only_deleted().all()
```

These methods are also available on {class}`~alchemiq.QuerySet` directly:

```python
from alchemiq import QuerySet
from myapp.models import Article

qs = QuerySet(Article).with_deleted().filter(title__icontains="draft")
results = await qs.all()
```

### Deleted-mode constants

The ``_deleted`` parameter on {class}`~alchemiq.QuerySet` accepts one of three
string constants from ``alchemiq.query.soft_delete``:

| Constant | Value | Effect |
|---|---|---|
| ``EXCLUDE`` | ``"exclude"`` | Default - live rows only (``deleted_at IS NULL``) |
| ``INCLUDE`` | ``"include"`` | Live **and** deleted rows (no filter on ``deleted_at``) |
| ``ONLY`` | ``"only"`` | Deleted rows only (``deleted_at IS NOT NULL``) |

---

## Relationships and joins

The liveness filter follows the query through relationships, not just the root
model.  By default (``EXCLUDE`` mode):

- ``prefetch_related()`` collections contain live rows only;
- a ``select_related()`` target that has been soft-deleted loads as ``None``
  (the foreign-key column keeps its value);
- traversal filters such as ``filter(author__name="Bob")`` do not match
  through a tombstoned ``author``;
- ``to_dict(relations=...)`` therefore never serializes tombstones.

``with_deleted()`` lifts the filter for the **whole statement** - relationship
loads and joins included:

```python
post = await posts.with_deleted().select_related("author").get(id=3)
post.author  # loaded even if the author is soft-deleted
```

``only_deleted()`` applies to the root model only; relations of a tombstoned
row load **unfiltered** so that administrative and restore tooling can see the
full picture.

Two escape hatches bypass the filter entirely: ``repo.restore()`` /
``repo.hard_delete()`` (they must reach tombstones), and any session you
create yourself with native SQLAlchemy - the filter is attached only to
sessions created by alchemiq.

---

## Restoring a deleted row

```python
article = await articles.restore(42)
# deleted_at is cleared; the row rejoins the live set.
```

``restore()`` raises ``ConfigError`` if called on a non-soft-delete model and
``NotFoundError`` if no tombstoned row with that primary key exists.

---

## Hard deletion

When you need to remove the physical row regardless of its deletion state, use
``hard_delete()``:

```python
await articles.hard_delete(42)
# The row is gone from the database.
```

``hard_delete()`` fires the ``pre_delete`` / ``post_delete`` signals and works
on both live and already soft-deleted rows.

---

## Serialization note

``to_dict()`` serializes every column declared on the model, including the
injected ``deleted_at`` key.  ``to_schema()`` exposes ``deleted_at`` as a field
in the generated Pydantic class.  A live row will have ``"deleted_at": None``
in the serialized output; a tombstoned row will carry the timestamp:

```python
data = article.to_dict(mode="json")
# {"id": 42, "title": "...", "deleted_at": "2025-03-01T12:00:00+00:00"}
```

Exclude it explicitly when it should not appear in API responses:

```python
data = article.to_dict(exclude={"deleted_at"})
```
