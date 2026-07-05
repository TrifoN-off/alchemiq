"""Declarative base class ``Model`` and its metaclass wiring."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Literal, Self

from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm.exc import DetachedInstanceError

from alchemiq.exceptions import ConfigError, RelationNotLoaded, ValidationError
from alchemiq.model.meta_options import parse_meta
from alchemiq.model.pipeline import (
    _apply_table_args,
    apply_version_mapper_args,
    install_descriptors,
    prepare_fields,
    reconcile_native_fields,
    register_validators,
)
from alchemiq.model.registry import mapper_registry, metadata
from alchemiq.types.strings import install_password_check

_CAMEL = re.compile(r"(?<!^)(?=[A-Z])")


def _snake(name: str) -> str:
    return _CAMEL.sub("_", name).lower()


class Model(DeclarativeBase):
    """Annotation-first declarative base for all alchemiq models.

    Subclass ``Model`` and declare fields as plain Python annotations - no
    ``mapped_column`` boilerplate required.  The metaclass resolves each
    annotation to the appropriate :class:`.FieldType`, wires the SQLAlchemy
    column, and installs validators.

    E.g.::

        class User(Model):
            id: PK[int]
            name: str
            email: Email

        class Post(Model):
            id: PK[int]
            author: User = ForeignKey(related_name="posts")
            title: str

    **Table name** defaults to the snake_case class name (no pluralization).
    Override ``__tablename__`` explicitly to use a different name.

    **Behaviour flags** are set via an inner ``class Meta``::

        class Article(Model):
            id: PK[int]
            body: str

            class Meta:
                soft_delete = True   # adds deleted_at; enables restore / hard_delete
                versioned   = True   # adds _version; enables optimistic locking
                timestamps  = True   # adds created_at / updated_at
                outbox      = True   # captures mutations for the transactional outbox

    .. seealso:: :class:`.Repository` - the async query/mutation API over a Model.
    """

    __abstract__ = True
    registry = mapper_registry
    metadata = metadata

    def check_password(self, raw: str) -> bool:
        """Verify *raw* against the stored password hash (whatever scheme produced it).

        This stub is replaced at class-definition time on any model that
        declares a :class:`.Password` field.  Calling it on a model with no
        ``Password`` field raises ``ConfigError``.

        E.g.::

            user = User(id=1, email="a@b.com", password="s3cr3t")
            assert user.check_password("s3cr3t") is True
            assert user.check_password("wrong") is False

        :param raw: the plaintext password to verify.
        :return: ``True`` if *raw* matches the stored hash, ``False`` otherwise.
        :raises ConfigError: if the model has no ``Password`` field.
        """
        raise ConfigError(
            f"{type(self).__name__} has no Password field; "
            "check_password() is only available on models that declare a Password field."
        )

    def to_dict(
        self,
        *,
        include: Any = None,
        exclude: Any = None,
        mode: Literal["python", "json"] = "python",
        relations: Any = (),
    ) -> dict[str, Any]:
        """Serialize own columns (and optionally loaded relations) to a plain dict.

        ``Password`` fields are omitted unless explicitly listed in ``include``.
        ``Maybe[T]`` columns are unwrapped: ``Some(v)`` -> ``v``, ``Nothing`` -> ``None``.
        On a soft-delete model the auto-injected ``deleted_at`` key IS present.

        E.g.::

            user = User(id=1, email="ada@x.io", password="s3cr3t")
            d = user.to_dict()                         # password omitted
            d = user.to_dict(mode="json")              # datetime -> ISO string
            d = user.to_dict(include={"id", "email"})  # whitelist
            d = user.to_dict(exclude={"created_at"})   # blacklist

        :param include: field names to include (whitelist); ``None`` means all.
        :param exclude: field names to omit (blacklist); ``None`` means none.
        :param mode: ``"python"`` keeps native types (``datetime``, ``Decimal``);
            ``"json"`` coerces them to JSON-safe scalars (ISO strings, ``str``).
        :param relations: names of eagerly-loaded relationship attributes to inline.
        :return: a plain ``dict`` keyed by field name.
        :raises RelationNotLoaded: if a name in *relations* was not joined in the query.

        .. seealso:: :meth:`.Model.to_pydantic` - validated Pydantic DTO.
        """
        from alchemiq.model.serialization import to_dict

        return to_dict(self, include=include, exclude=exclude, mode=mode, relations=relations)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        """Construct an instance from a plain dict, validating field names and types.

        Unknown keys raise ``ValidationError`` immediately (fail-fast).
        Known keys are passed through the same set-event validators as normal
        assignment, so ``Email`` is normalised, ``Password`` is hashed, etc.

        E.g.::

            acc = Account.from_dict(
                {"id": 9, "email": "X@Y.com", "password": "pw"}
            )
            assert acc.email == "x@y.com"    # normalised
            assert acc.check_password("pw")  # hashed on assignment

        :param data: a mapping of field names to raw values.
        :return: a new instance of this model class.
        :raises ValidationError: if *data* contains keys that are not fields; an
            aggregated error is also raised if any per-field validator rejects a value.
        """
        from alchemiq.model.serialization import from_dict

        return from_dict(cls, data)

    @classmethod
    def to_schema(cls, *, include: Any = None, exclude: Any = None) -> Any:
        """Return a Pydantic model class whose fields mirror this model's columns.

        The schema class is built once and cached per ``(include, exclude)`` pair.
        ``Password`` fields are excluded by default (same policy as
        :meth:`.Model.to_dict`).

        E.g.::

            AccountSchema = Account.to_schema()
            AccountSchema = Account.to_schema(exclude={"created_at"})
            instance = AccountSchema(id=1, email="a@b.com")

        :param include: field names to include (whitelist).
        :param exclude: field names to omit (blacklist).
        :return: a ``pydantic.BaseModel`` subclass named ``<Model>Schema``.

        .. seealso:: :meth:`.Model.to_pydantic` - convert an *instance* to a schema DTO.
        """
        from alchemiq.model.serialization import build_schema

        return build_schema(cls, include=include, exclude=exclude)

    def to_pydantic(self) -> Any:
        """Convert this instance to a validated Pydantic schema object.

        Equivalent to ``Model.to_schema().model_validate(self.to_dict())``.
        ``Password`` fields are excluded; ``Maybe[T]`` columns are unwrapped.

        E.g.::

            dto = user.to_pydantic()
            assert dto.email == "ada@x.io"

        :return: a validated instance of the Pydantic class returned by
            :meth:`.Model.to_schema`.

        .. seealso:: :meth:`.Model.to_schema` - the generated Pydantic class itself.
        """
        from alchemiq.model.serialization import to_pydantic

        return to_pydantic(self)

    def __getattribute__(self, name: str) -> Any:
        # Fast path: private/dunder names bypass the translation shim entirely.
        # This deliberate perf tradeoff is the only way to deliver
        # typed RelationNotLoaded on bare obj.rel access; the happy path costs
        # one guarded object.__getattribute__ call per public attribute access.
        # Note: relationship names with a leading underscore would not be translated
        # here (they'd surface as a raw SQLAlchemy error (InvalidRequestError or
        # DetachedInstanceError)). In practice all alchemiq relationship names are
        # public identifiers so this gap has no impact.
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        try:
            return object.__getattribute__(self, name)
        except (InvalidRequestError, DetachedInstanceError) as exc:
            from alchemiq.model.pipeline import register_native_relationships

            register_native_relationships(type(self))
            rels = getattr(type(self), "__alchemiq_relationships__", {})
            if name in rels:
                raise RelationNotLoaded(
                    f"{type(self).__name__}.{name} is not loaded; add "
                    f".select_related({name!r}) or .prefetch_related({name!r}) to the query"
                ) from exc
            raise

    def __init_subclass__(cls, **kwargs: Any) -> None:
        # Parse and attach MetaOptions before anything else so that abstract
        # base classes propagate their Meta to concrete subclasses via MRO.
        cls.__alchemiq_meta__ = parse_meta(cls)

        # Each concrete class owns its own relationship registry dict.
        if "__alchemiq_relationships__" not in cls.__dict__:
            cls.__alchemiq_relationships__ = {}  # type: ignore[attr-defined]

        # Skip further setup for abstract intermediates.
        if cls.__dict__.get("__abstract__", False):
            super().__init_subclass__(**kwargs)
            return

        # Auto-derive table name from class name as snake_case if not set.
        # An explicit class-level __tablename__ wins; Meta.table_name is next;
        # snake_case default is the fallback.
        if "__tablename__" not in cls.__dict__:
            cls.__tablename__ = cls.__alchemiq_meta__.table_name or _snake(cls.__name__)  # type: ignore[attr-defined]

        fields = prepare_fields(cls)
        _apply_table_args(cls)
        apply_version_mapper_args(cls)
        super().__init_subclass__(**kwargs)
        reconcile_native_fields(cls, fields)
        register_validators(cls, fields)
        install_descriptors(cls, fields)
        install_password_check(cls, fields)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__()
        errors: list[ValidationError] = []
        for key, value in kwargs.items():
            try:
                setattr(self, key, value)
            except ValidationError as e:
                errors.append(e)
        if errors:
            raise ValidationError.aggregate(errors, model=type(self).__name__)
