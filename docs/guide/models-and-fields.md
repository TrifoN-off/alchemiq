# Models and field types

Declare a database table as a Python class that subclasses {class}`~alchemiq.Model`.
No `Column()`, no `mapped_column()`, no SQLAlchemy boilerplate - you describe
**what** the data is; alchemiq handles **how** it is stored.

```python
from alchemiq import Model
from alchemiq.types import PK, Email

class User(Model):
    id: PK[int]
    name: str
    email: Email
```

The table name defaults to the snake_case class name (`user`).
Override it with an explicit `__tablename__` class attribute or via
`Meta.table_name`.

---

## Field declaration forms

### Bare annotation

Write the field type directly as an annotation.
Alchemiq instantiates the type with default settings:

```python
class Article(Model):
    id: PK[int]
    title: str          # plain text column, VARCHAR
    email: Email        # validated email, VARCHAR(320)
    score: NonNegative  # int >= 0
```

### Configured value slot

Pass a {class}`~alchemiq.Field` (or any field-type instance) on the right-hand side
to customise column behaviour:

```python
from alchemiq import Field, Model
from alchemiq.types import PK, Bounded, Email

class Article(Model):
    id: PK[int]
    title: str    = Field(max_length=200, index=True)
    score: int    = Bounded(0, 100)
    email: Email  = Email(unique=True)
```

{class}`~alchemiq.Field` accepts: `nullable`, `unique`, `index`,
`default`, `server_default`, `max_length`, `onupdate`.
Any semantic field type (`Bounded`, `Email`, etc.) accepts the same
keyword arguments in addition to its own.

### Optional fields with `Maybe[T]`

For nullable columns with explicit optional semantics use `Maybe[T]`:

```python
from alchemiq.types import Maybe, Some, Nothing

class Profile(Model):
    id: PK[int]
    bio: Maybe[str]         # NULL-safe optional
```

Assign `Some(value)` or `Nothing`.
Plain `str | None` is also accepted for simple cases.
For semantic types prefer `Maybe[Email]` over `Email | None`.

---

## Primary keys - `PK[T]`

`PK[int]` produces a BIGINT autoincrement primary key column named `id`
(or whatever you call the field):

```python
class Tag(Model):
    id: PK[int]
    name: str
```

Alternative PK types are available from `alchemiq.types`:

| Type | Storage | Default |
|---|---|---|
| `PK[int]` | `BIGINT` autoincrement | - |
| `UUID4` | PostgreSQL `UUID` | `uuid.uuid4` |
| `UUID7` | PostgreSQL `UUID` (time-ordered) | `uuid7()` |
| `NanoID` | `VARCHAR(21)` | `nanoid()` |

A native `Mapped[...] = mapped_column(primary_key=True)` column
is also recognized as the primary key - see the
[native columns guide](native-columns.md).

---

## Built-in field types

All types live in `alchemiq.types`.

### String types

| Type | Validation / behaviour | Storage |
|---|---|---|
| `Email` | Strips, lowercases, validates syntax | `VARCHAR(320)` |
| `Phone` | E.164 format | `VARCHAR(16)` |
| `URL` | http/https with non-empty host | `VARCHAR(2048)` |
| `Slug` | `[a-z0-9-]+`, no consecutive hyphens | `VARCHAR(80)` |
| `Password` | Hashes with scrypt; exposes `check_password()` | `VARCHAR(255)` |

### Password hashing

`Password` hashes values automatically on write.
The default algorithm is **scrypt** (Python stdlib - no extra package required).

To switch the global backend, call
{func}`~alchemiq.configure_password_hashing` once at application startup:

```python
import alchemiq

alchemiq.configure_password_hashing("argon2")   # requires pip install "alchemiq[argon2]"
```

Supported scheme names:

| Scheme | Extra | Notes |
|---|---|---|
| `"scrypt"` | *(none - stdlib)* | Default |
| `"argon2"` | `[argon2]` | `argon2-cffi` |
| `"bcrypt"` | `[bcrypt]` | **Truncates passwords at 72 bytes** |

`check_password()` dispatches on the algorithm prefix embedded
in the stored hash, so it authenticates correctly across schemes.
Hashes stored under the previous algorithm remain valid after a switch;
rows are re-hashed with the new algorithm only when the user next sets a
password, enabling seamless scheme migration without a bulk re-hash.

To restore the default, call {func}`~alchemiq.reset_password_hashing`.

### Numeric types

| Type | Validation / behaviour | Storage |
|---|---|---|
| `Bounded(min, max)` | Inclusive range check | `BIGINT` |
| `Positive` | >= 1 | `BIGINT` |
| `NonNegative` | >= 0 | `BIGINT` |
| `Percent` | 0-100 inclusive | `BIGINT` |
| `Money(scale=2)` | Stored as integer minor units, read as `Decimal` | `BIGINT` |
| `RoundedDecimal(places=2)` | Fixed-precision decimal with ROUND_HALF_EVEN | `NUMERIC(38, places)` |

### Temporal types

| Type | Behaviour | Storage |
|---|---|---|
| `DateTimeTz` | Timezone-aware datetime | `TIMESTAMPTZ` |
| `Date` | Date only | `DATE` |
| `Time` | Time only | `TIME` |
| `UnixTimestamp` | Stores as integer, returns `datetime` | `BIGINT` |
| `CreatedAt` | Auto-set on insert | `TIMESTAMPTZ` |
| `UpdatedAt` | Auto-updated on every write | `TIMESTAMPTZ` |

### Special types

| Type | Behaviour |
|---|---|
| `JSON` | JSONB column with optional Pydantic schema validation |
| `Array[T]` | PostgreSQL array with element typing |
| `Encrypted` | Transparent AES encryption before write, decryption on read |
| `Enum` | Python `enum.Enum` with auto-created PostgreSQL `ENUM` type |

---

## Eager validation

Every assignment to a field triggers the field type's `validate()` method.
This happens at construction time (`User(email="bad")`) and on bare attribute
assignment (`user.email = "bad"`):

```python
from alchemiq.exceptions import ValidationError

user = User(id=1, name="Ada", email="not-an-email")
# raises ValidationError immediately

user = User(id=1, name="Ada", email="ada@example.com")
user.email = "bad"   # also raises ValidationError
```

Native `Mapped[...] = mapped_column(...)` columns are the one exception -
they carry no eager validation (they are an escape hatch whose correctness
is the caller's responsibility).

---

## The `Meta` class

Place an inner `class Meta` on your model to configure behaviour flags,
indexes, and constraints:

```python
from alchemiq.model.meta_options import Index, Unique, Check

class Article(Model):
    id: PK[int]
    slug: str
    author_id: int
    published_at: DateTimeTz

    class Meta:
        soft_delete = True      # adds deleted_at; enables restore / hard_delete
        timestamps  = True      # adds created_at / updated_at automatically
        versioned   = True      # adds _version; enables optimistic locking -> 409
        outbox      = True      # captures mutations for the transactional outbox
        table_name  = "articles"
        schema      = "content"
        indexes     = [Index("slug", unique=True), Index("author_id")]
        constraints = [Unique("slug", "author_id"), Check("published_at IS NOT NULL")]
```

**Behaviour flags:**

| Flag | Effect |
|---|---|
| `soft_delete` | Injects `deleted_at TIMESTAMPTZ NULL`; all queries exclude soft-deleted rows |
| `timestamps` | Injects `created_at` and `updated_at` with auto-set / auto-update |
| `versioned` | Injects `_version BIGINT`; update/delete with a stale version raises `ConcurrentModificationError` (409) |
| `outbox` | All mutations are captured for the transactional outbox pattern |

**Table configuration:**

| Option | Effect |
|---|---|
| `abstract` | Make a base/mixin model that creates no table of its own (see below) |
| `table_name` | Override the auto-derived snake_case table name |
| `schema` | Place the table in a named PostgreSQL schema |
| `indexes` | List of `Index(*columns, unique=False)` DDL indexes |
| `constraints` | List of `Unique(*columns)` or `Check(expression)` constraints |

### Abstract base models

Set `Meta.abstract = True` to declare a base (or mixin) model that defines fields
and flags for subclasses to inherit, but maps to no table of its own:

```python
class Auditable(Model):
    class Meta:
        abstract = True
        timestamps = True   # inherited by every concrete subclass

class Article(Auditable):
    id: PK[int]
    title: str
    # gets created_at / updated_at from Auditable; only Article maps to a table
```

Flags and fields declared on an abstract base are inherited by all concrete subclasses;
only the concrete subclasses produce database tables.
