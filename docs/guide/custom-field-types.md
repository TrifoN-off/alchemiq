# Writing a custom field type

All built-in field types in alchemiq are subclasses of {class}`~alchemiq.types.FieldType`.
You can extend the system with your own types by subclassing it directly and implementing
the three members below.

For columns that alchemiq cannot model at all (JSONB, `TypeDecorator`, computed columns),
see the [native columns guide](native-columns.md) instead.

---

| Member | Purpose |
|---|---|
| `python_type` | The Python type the field holds (e.g. `str`, `int`) |
| `column_type()` | Returns the SQLAlchemy `TypeEngine` (or `TypeDecorator`) for storage |
| `validate(value)` | Called on every assignment; return the (normalized) value or raise `ValidationError` |

## Minimal example

```python
from sqlalchemy import String
from alchemiq.types import FieldType
from alchemiq.exceptions import ValidationError

class Upper(FieldType):
    python_type = str

    def column_type(self):
        return String(self.config.max_length or 255)

    def validate(self, value):
        if not isinstance(value, str):
            raise ValidationError(reason="must be a string", value=value)
        return value.upper()
```

## Using your custom type on a model

**Bare annotation** - alchemiq instantiates `Upper()` with defaults:

```python
from alchemiq import Model
from alchemiq.types import PK

class Product(Model):
    id: PK[int]
    code: Upper          # bare: Upper() is constructed automatically
```

**Configured instance** - pass kwargs such as `unique`, `index`, or `max_length`:

```python
class Product(Model):
    id: PK[int]
    code: str = Upper(unique=True, max_length=20)
```

Both forms call `Upper.validate()` on every assignment and map to the SQLAlchemy type returned by `Upper.column_type()`.

## Optional: supporting `FieldType[inner]` subscript syntax

If your type wraps an inner element type, implement `__class_getitem__`:

```python
class Prefixed(FieldType):
    python_type = str

    def __init__(self, prefix: str = "", **kw):
        super().__init__(**kw)
        self.prefix = prefix

    def __class_getitem__(cls, prefix: str) -> "Prefixed":
        return cls(prefix=prefix)

    def column_type(self):
        return String()

    def validate(self, value):
        s = str(value)
        return s if s.startswith(self.prefix) else self.prefix + s
```

Usage: `code: Prefixed["SKU-"]` or `code: str = Prefixed("SKU-", unique=True)`.
