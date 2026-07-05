# Serialization

Every alchemiq model can serialize itself to a plain dictionary, convert to a
validated Pydantic object, or generate a reusable Pydantic schema class.
All three paths respect ``include``/``exclude`` filtering and handle special
column types such as ``Maybe[T]`` and ``Password`` automatically.

---

## `to_dict` - serialize to a dictionary

```python
data = instance.to_dict()
```

### Mode

The ``mode`` keyword controls how values are coerced:

| Mode | Behaviour |
|---|---|
| ``"python"`` (default) | Native Python types: ``datetime``, ``Decimal``, ``UUID``, ``Enum`` values are kept as-is |
| ``"json"`` | JSON-safe scalars: ``datetime``/``date``/``time`` -> ISO string; ``Decimal``/``UUID`` -> ``str``; ``Enum`` -> ``.value`` |

```python
# Python-native values
d = user.to_dict()                  # datetime stays a datetime object

# JSON-ready values
d = user.to_dict(mode="json")       # datetime -> "2025-03-01T12:00:00+00:00"
```

### Field selection

```python
# Include only specific fields
d = user.to_dict(include={"id", "email"})

# Exclude specific fields
d = user.to_dict(exclude={"created_at", "updated_at"})
```

``Password`` fields are omitted unless explicitly listed in ``include``.

### Inlining relations

Pass eagerly-loaded relationship names via ``relations`` to inline them
recursively:

```python
d = order.to_dict(relations=("items",))
# {"id": 1, "status": "paid", "items": [{"id": 10, ...}, ...]}
```

---

## `Maybe[T]` unwrapping

Columns declared as ``Maybe[T]`` always hold either ``Some(value)`` or
``Nothing`` on the model instance.  Both ``to_dict`` modes unwrap the
container automatically:

- In ``"python"`` mode: ``Some(v)`` -> ``v``, ``Nothing`` -> ``None``
- In ``"json"`` mode: ``Some(v)`` -> coerced scalar, ``Nothing`` -> ``None``

```python
from alchemiq.types import Maybe, Some, Nothing

class Profile(Model):
    id: PK[int]
    bio: Maybe[str]

profile.bio = Some("Hello")
profile.to_dict()            # {"id": 1, "bio": "Hello"}

profile.bio = Nothing
profile.to_dict()            # {"id": 1, "bio": None}
```

The unwrapping happens in both modes, so you never see raw ``Some``/``Nothing``
objects in the output.

---

## `to_schema` - generate a Pydantic schema class

``to_schema()`` is a classmethod that builds and caches a ``pydantic.BaseModel``
subclass whose fields mirror the model's columns:

```python
UserSchema = User.to_schema()
UserPublicSchema = User.to_schema(exclude={"password_hash"})
```

The result is a standard Pydantic class.  Use it for FastAPI request/response
typing, manual validation, or JSON serialisation:

```python
schema = User.to_schema(include={"id", "name", "email"})
validated = schema.model_validate({"id": 1, "name": "Ada", "email": "ada@example.com"})
```

The schema is memoised per ``(include, exclude)`` pair on the model class, so
repeated calls with the same arguments return the same class object.
``Password`` fields are excluded unless explicitly whitelisted in ``include``.

---

## `to_pydantic` - convert an instance to a schema object

``to_pydantic()`` calls ``to_schema()`` and ``to_dict(mode="python")``
internally, then validates the dict through the schema:

```python
dto = user.to_pydantic()
# dto is a pydantic.BaseModel instance - fully validated
print(dto.model_dump())
```

It is equivalent to:

```python
User.to_schema().model_validate(user.to_dict(mode="python"))
```

Use ``to_pydantic()`` when you need a typed, validated DTO to pass between
layers, and ``to_dict(mode="json")`` when you need a JSON-serialisable dict
directly.
