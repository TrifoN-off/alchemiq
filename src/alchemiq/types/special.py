"""Special-purpose field types: JSON, Array, Enum, and Encrypted."""

from __future__ import annotations

import enum as _enum
from typing import Any

from sqlalchemy import Enum as SaEnum
from sqlalchemy import LargeBinary
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.types import TypeDecorator, TypeEngine

from alchemiq.exceptions import ValidationError
from alchemiq.types.base import FieldType


class JSON(FieldType[dict]):
    """JSONB column with optional Pydantic model validation.

    When ``model`` is provided, ``validate()`` runs ``model(**value).model_dump()``
    and raises ``ValidationError`` if the value does not conform.
    """

    python_type = dict

    def __init__(self, model: type | None = None, **kw: Any) -> None:
        super().__init__(**kw)
        self.model = model

    def column_type(self) -> TypeEngine[Any]:
        """Return ``JSONB``."""
        return JSONB()

    def validate(self, value: Any) -> Any:
        """Validate ``value`` against the Pydantic model if one was provided."""
        if self.model is None:
            return value
        try:
            import pydantic

            return self.model(**value).model_dump()
        except pydantic.ValidationError as e:
            raise ValidationError(
                reason=f"JSON does not match {self.model.__name__}", value=value
            ) from e


class Array[T](FieldType[list[T]]):
    """PostgreSQL ``ARRAY`` column; each element is validated via the inner field.

    Use ``Array[int]`` sugar or ``Array(inner_field)`` for custom inner types.
    """

    python_type = list

    def __init__(self, inner: FieldType, **kw: Any) -> None:
        super().__init__(**kw)
        self.inner = inner

    def __class_getitem__(cls, inner: Any) -> Array:
        from alchemiq.types.base import Field

        return cls(Field(python_type=inner))

    def column_type(self) -> TypeEngine[Any]:
        """Return ``ARRAY(inner.column_type())``."""
        return ARRAY(self.inner.column_type())

    def validate(self, value: Any) -> Any:
        """Validate each element through the inner field's ``validate`` method."""
        return [self.inner.validate(v) for v in value]


class Enum[E: _enum.Enum](FieldType[E]):
    """PostgreSQL native enum column backed by a SQLAlchemy ``SaEnum`` with ``create_type=True``.

    Use ``Enum[MyEnum]`` sugar or ``Enum(MyEnum)`` directly.
    """

    def __init__(self, enum_cls: type[_enum.Enum], **kw: Any) -> None:
        super().__init__(python_type=enum_cls, **kw)
        self.enum_cls = enum_cls

    def __class_getitem__(cls, item: type[_enum.Enum]) -> Any:
        return cls(item)

    def column_type(self) -> TypeEngine[Any]:
        """Return ``SaEnum(enum_cls, create_type=True)``."""
        return SaEnum(self.enum_cls, create_type=True)


class _EncryptedType(TypeDecorator[Any]):
    """``LargeBinary`` TypeDecorator that encrypts on write and decrypts on read."""

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> bytes | None:
        """Encrypt ``value`` to bytes before writing to the database."""
        if value is None:
            return None
        from alchemiq._internal.crypto import encrypt

        return encrypt(str(value).encode())

    def process_result_value(self, value: bytes | None, dialect: Any) -> Any:
        """Decrypt bytes read from the database back to a string."""
        if value is None:
            return None
        from alchemiq._internal.crypto import decrypt

        return decrypt(value).decode()


class Encrypted[T](FieldType[T]):
    """Encrypted-at-rest column backed by ``LargeBinary``.

    The plaintext is converted to ``str``, encrypted to bytes with AES-GCM, and
    stored as a ``LargeBinary`` column.  On read the bytes are decrypted
    transparently and returned as a string.  Use ``Encrypted[str]`` (default) or
    ``Encrypted[T]`` to declare the Python-side type.

    Requires the ``alchemiq[crypto]`` extra (``cryptography`` package).

    E.g.::

        class Credential(Model):
            id: PK[int]
            payload: Encrypted[str]   # or just: payload: Encrypted

    The encryption key is supplied by a key provider registered at application
    startup.

    .. warning::

        This field stores *ciphertext* in the database column.  The column
        value returned by a raw SQL query is opaque bytes, not the plaintext.

    .. seealso:: :class:`.Password` - hashed (not reversible) string storage.
    """

    python_type = str

    def __init__(self, inner: type = str, **kw: Any) -> None:
        super().__init__(python_type=inner, **kw)

    def __class_getitem__(cls, inner: type) -> Encrypted:
        return cls(inner)

    def column_type(self) -> TypeEngine[Any]:
        """Return ``_EncryptedType`` backed by ``LargeBinary``."""
        return _EncryptedType()
