# Relationships

Alchemiq infers relationship type from the annotation alone in most cases.
Override markers are available when you need to customise the join-table name,
override the reverse accessor, or control `ON DELETE` behaviour.

---

## Many-to-one (`ForeignKey`)

A plain model annotation (required or optional) creates a many-to-one FK column:

```python
from alchemiq import Model
from alchemiq.types import PK

class Org(Model):
    id: PK[int]
    name: str

class Member(Model):
    id: PK[int]
    org: Org              # required - adds org_id FK, ON DELETE RESTRICT
    sponsor: Org | None   # optional - adds sponsor_id FK, ON DELETE SET NULL
```

Alchemiq adds the `<name>_id` FK column automatically and wires a `<snake_cls>_set`
reverse collection on the target model (`org.member_set`).

Use {class}`~alchemiq.ForeignKey` to customise `on_delete` or the reverse accessor
name:

```python
from alchemiq import ForeignKey

class Member(Model):
    id: PK[int]
    org: Org = ForeignKey(on_delete="CASCADE", related_name="members")
```

When two FK fields on the same model point to the same target, at least one must
declare a distinct `related_name` to avoid a collision.

---

## Many-to-many (`ManyToMany`)

Annotate a field as `list[TargetModel]` to declare an M2M relationship.
Alchemiq creates a hidden join table whose name is derived from the two table names,
sorted and joined with `_`.
A reverse collection `<snake_cls>_set` is added to the target model.

```python
class Tag(Model):
    id: PK[int]
    name: str

class Post(Model):
    id: PK[int]
    title: str
    tags: list[Tag]       # auto join-table; reverse: Tag.post_set
```

Load the collection with `prefetch_related("tags")`;
filter through the join with `filter(tags__name="python")`.

### Two M2M fields to the same model

When two M2M fields on the same model both point to the same target, the auto-derived
join-table names collide.
Use {class}`~alchemiq.ManyToMany` to supply explicit names for both:

```python
class Post(Model):
    id: PK[int]
    tags: list[Tag]
    featured: list[Tag] = ManyToMany(
        related_name="featured_post_set",
        secondary="post_featured_tag",
    )
```

`ManyToMany` parameters:

| Parameter | Default | Effect |
|---|---|---|
| `related_name` | `<snake_cls>_set` | Name of the reverse collection on the target |
| `secondary` | sorted table names joined with `_` | Explicit name for the join table |

### Limitations

Self-referential M2M and through-models (join tables with extra columns) are not
supported by the `list[Model]` sugar.
Use a native `relationship(secondary=...)` for those cases - see the
{ref}`native columns guide <native-relationship-escape-hatch>`.

---

## One-to-one (`OneToOne`)

{class}`~alchemiq.OneToOne` wraps a generic parameter and wires a `UNIQUE`, `NOT NULL`
FK column plus a scalar reverse accessor:

```python
class Profile(Model):
    id: PK[int]
    bio: str

class User(Model):
    id: PK[int]
    profile: OneToOne[Profile]
    # adds: profile_id FK (unique, NOT NULL)
    # reverse: Profile.user (scalar, not a collection)
```

Under `TYPE_CHECKING`, `OneToOne[T]` resolves to `T`, so static analysers infer the
correct type without any extra stubs.

The reverse accessor name is `_snake(User)` -> `user` (singular, not `user_set`).

---

## Soft delete and relationships

When a related model has `Meta.soft_delete = True`, its tombstones are
filtered out of relationship loads and traversal joins as well: prefetched
collections contain live rows only, a soft-deleted `select_related()` target
loads as `None`, and `filter(author__name=...)` does not match through a
tombstoned author.  `with_deleted()` lifts the filter for the whole statement,
relations included.  See the "Relationships and joins" section in
[Soft delete](soft-delete.md).

---

## Native `relationship()` escape hatch

For relationships the alchemiq markers do not cover - through-model M2M,
self-referential M2M, or any fully custom join condition - use a native SQLAlchemy
`relationship()` directly:

```python
from sqlalchemy.orm import Mapped, relationship

post_tag = ...  # a SQLAlchemy Table for the association table

class Post(Model):
    id: PK[int]
    tags: Mapped[list[Tag]] = relationship(secondary=post_tag, lazy="raise_on_sql")
```

Alchemiq skips native `relationship()` declarations during field preparation
(detected via the `NATIVE_RELATIONSHIP` sentinel) and registers them lazily in
`__alchemiq_relationships__` the first time the attribute is accessed.
Once registered, they work with `select_related` and `prefetch_related` by name.

See {ref}`native columns - native relationship escape hatch <native-relationship-escape-hatch>`
for the full explanation.
