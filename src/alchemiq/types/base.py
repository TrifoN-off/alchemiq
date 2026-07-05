"""Core field-type abstractions: FieldConfig, FieldType, Field, and _NativeField."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self, overload

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeEngine


class _Missing:
    def __repr__(self) -> str:
        return "<MISSING>"


_MISSING: Any = _Missing()


@dataclass(frozen=True)
class FieldConfig:
    """Immutable column-level configuration passed to ``mapped_column``."""

    nullable: bool = False
    unique: bool = False
    index: bool = False
    primary_key: bool = False
    default: Any = _MISSING
    server_default: Any = None
    max_length: int | None = None
    onupdate: Any = None


class FieldType[T](ABC):
    """Base of every Alchemiq field type. Public, user-subclassable."""

    python_type: type = object

    def __init__(
        self,
        *,
        python_type: type | None = None,
        unique: bool = False,
        index: bool = False,
        primary_key: bool = False,
        nullable: bool = False,
        default: Any = _MISSING,
        server_default: Any = None,
        max_length: int | None = None,
        onupdate: Any = None,
    ) -> None:
        if python_type is not None:
            self.python_type = python_type
        self.config = FieldConfig(
            nullable=nullable,
            unique=unique,
            index=index,
            primary_key=primary_key,
            default=default,
            server_default=server_default,
            max_length=max_length,
            onupdate=onupdate,
        )

    if TYPE_CHECKING:
        # Typing-only descriptor protocol. These stubs make a bare annotation
        # (`email: Email`) resolve to its python type for the checker, exactly like
        # SQLAlchemy's Mapped[T]. They do NOT exist at runtime (TYPE_CHECKING is
        # False), so FieldType instances are never real descriptors and the model
        # pipeline's mapped_column instrumentation is untouched.
        @overload
        def __get__(self, obj: None, owner: Any = None) -> Self: ...
        @overload
        def __get__(self, obj: object, owner: Any = None) -> T: ...
        def __get__(self, obj: Any, owner: Any = None) -> Any: ...
        def __set__(self, obj: object, value: T) -> None: ...

    @abstractmethod
    def column_type(self) -> TypeEngine[Any]:
        """SQLAlchemy storage type (or TypeDecorator) for this field."""

    def validate(self, value: Any) -> Any:
        """Eager validation + normalization. Override to enforce rules. Identity by default."""
        return value

    def descriptor(self, name: str) -> Any | None:
        """Optional custom descriptor (e.g. Password). None = use native instrumentation."""
        return None

    def build_column(self) -> Mapped[Any]:
        """Build and return the ``mapped_column`` for this field."""
        c = self.config
        kwargs: dict[str, Any] = {
            "nullable": c.nullable,
            "primary_key": c.primary_key,
            "unique": c.unique or None,
            "index": c.index or None,
        }
        if c.default is not _MISSING:
            kwargs["default"] = c.default
        if c.server_default is not None:
            kwargs["server_default"] = c.server_default
        if c.onupdate is not None:
            kwargs["onupdate"] = c.onupdate
        return mapped_column(self.column_type(), **kwargs)


class Field(FieldType[Any]):
    """Generic field for plain python-typed columns (str/int/...).

    python_type is set by the pipeline.
    """

    def column_type(self) -> TypeEngine[Any]:
        """Return the SQLAlchemy column type derived from ``python_type``."""
        if self.python_type is str:
            return String(self.config.max_length) if self.config.max_length else String()
        from sqlalchemy import (
            BigInteger,
            Boolean,
            Float,
            LargeBinary,
        )

        mapping: dict[type, TypeEngine[Any]] = {
            int: BigInteger(),
            float: Float(),
            bool: Boolean(),
            bytes: LargeBinary(),
        }
        try:
            return mapping[self.python_type]
        except KeyError as e:  # pragma: no cover - defensive
            from alchemiq.exceptions import ConfigError

            raise ConfigError(f"Field has no default column type for {self.python_type!r}") from e


class _NativeField(FieldType[Any]):
    """Passthrough field for a user-declared native SQLAlchemy column.

    Registered in ``__alchemiq_fields__`` so a ``Mapped[...] = mapped_column(...)`` column is
    first-class for querying, serialization, schema-building and pk discovery - but carries NO
    eager validation (escape hatch). The Column is owned by SQLAlchemy; ``build_column`` /
    ``column_type`` are never invoked by the pipeline for native fields. The ``config`` starts
    empty and is filled post-mapping by ``reconcile_native_fields``.
    """

    def __init__(self, python_type: type) -> None:
        self.python_type = python_type
        self.config = FieldConfig()

    def column_type(self) -> TypeEngine[Any]:  # pragma: no cover - SQLAlchemy owns the column
        from alchemiq.exceptions import ConfigError

        raise ConfigError("native field column is managed by SQLAlchemy, not built by alchemiq")
