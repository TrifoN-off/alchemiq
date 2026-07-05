"""String field types with built-in normalization and validation."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import String
from sqlalchemy.types import TypeEngine

from alchemiq._internal.hashing import hash_password, is_hashed, verify_password
from alchemiq.exceptions import ValidationError
from alchemiq.types.base import FieldType

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_E164_RE = re.compile(r"^\+[1-9]\d{1,14}$")


class Email(FieldType[str]):
    """Email address field - normalized to lowercase and validated against a basic syntax regex.

    Stored as ``VARCHAR(320)`` (the RFC 5321 maximum). Raises ``ValidationError``
    if the value is not a string or fails the ``local@domain.tld`` pattern check.
    """

    python_type = str

    def column_type(self) -> TypeEngine[Any]:
        """Return ``String(max_length or 320)``."""
        return String(self.config.max_length or 320)

    def validate(self, value: Any) -> Any:
        """Strip, lowercase, and validate the email address."""
        if not isinstance(value, str):
            raise ValidationError(reason="must be a string", value=value)
        normalized = value.strip().lower()
        if not _EMAIL_RE.match(normalized):
            raise ValidationError(reason="invalid email syntax", value=value)
        return normalized


class URL(FieldType[str]):
    """HTTP/HTTPS URL field validated via ``urlparse``.

    Stored as ``VARCHAR(2048)``. Raises ``ValidationError`` if the scheme is not
    ``http`` or ``https``, or if the netloc is empty.
    """

    python_type = str

    def column_type(self) -> TypeEngine[Any]:
        """Return ``String(max_length or 2048)``."""
        return String(self.config.max_length or 2048)

    def validate(self, value: Any) -> Any:
        """Validate that ``value`` is an http/https URL with a non-empty host."""
        parsed = urlparse(str(value))
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValidationError(reason="invalid URL", value=value)
        return str(value)


class Slug(FieldType[str]):
    """URL-slug field - normalized to lowercase and validated as ``^[a-z0-9]+(?:-[a-z0-9]+)*$``.

    Stored as ``VARCHAR(max_length)`` (default 80). Raises ``ValidationError``
    if the value contains characters outside the allowed set or has consecutive/
    leading/trailing hyphens.
    """

    python_type = str

    def __init__(self, max_length: int = 80, **kw: Any) -> None:
        super().__init__(max_length=max_length, **kw)

    def column_type(self) -> TypeEngine[Any]:
        """Return ``String(max_length)``."""
        return String(self.config.max_length)

    def validate(self, value: Any) -> Any:
        """Strip, lowercase, and validate the slug."""
        norm = str(value).strip().lower()
        if not _SLUG_RE.match(norm):
            raise ValidationError(reason="invalid slug", value=value)
        return norm


class Phone(FieldType[str]):
    """E.164 phone-number field. Strips spaces, parentheses, and dashes before validation.

    Stored as ``VARCHAR(16)``. Validates the E.164 format (``+<country><number>``);
    if the ``phonenumbers`` package is installed, also runs a region-aware validity
    check. Raises ``ValidationError`` on failure.
    """

    python_type = str

    def column_type(self) -> TypeEngine[Any]:
        """Return ``String(16)``."""
        return String(16)

    def validate(self, value: Any) -> Any:
        """Normalize and validate the phone number in E.164 format."""
        norm = re.sub(r"[\s()-]", "", str(value))
        if not _E164_RE.match(norm):
            raise ValidationError(reason="invalid E.164 phone", value=value)
        # Optional region validation if phonenumbers extra is installed.
        try:
            import phonenumbers  # ty: ignore[unresolved-import]
        except ImportError:
            return norm
        if not phonenumbers.is_valid_number(phonenumbers.parse(norm, None)):
            raise ValidationError(reason="not a valid phone number", value=value)
        return norm


class Password(FieldType[str]):
    r"""Mapped ``VARCHAR(255)`` column that eagerly hashes plaintext on assignment.

    The set-event validator (``validate()``) receives the plaintext, hashes it
    with the configured scheme (default ``scrypt``; see
    :func:`~alchemiq.configure_password_hashing`), and stores the hash directly
    in the column.  If the value is already a stored hash of any supported scheme
    (e.g. rehydrated from the DB) it is passed through unchanged to avoid
    double-hashing.

    A ``check_password(raw) -> bool`` method is injected onto the model instance
    by ``install_password_check`` during class creation.  It verifies *raw*
    against whatever scheme produced the stored hash.

    E.g.::

        class User(Model):
            id: PK[int]
            secret: Password

        user = User(id=1, secret="s3cr3t")
        assert user.secret != "s3cr3t"          # hashed (scrypt by default)
        assert user.check_password("s3cr3t")    # True
        assert not user.check_password("wrong") # False

    .. note::

        ``Password`` fields are excluded from :meth:`.Model.to_dict` and
        :meth:`.Model.to_schema` output by default.  Pass
        ``include={"secret"}`` to opt in.

    .. warning::

        Only one ``Password`` field per model is supported.  Declaring a second
        one raises ``ConfigError`` at class-definition time.

    .. seealso:: :meth:`.Model.check_password`, :func:`~alchemiq.configure_password_hashing`
    """

    python_type = str

    def column_type(self) -> TypeEngine[Any]:
        """Return ``String(255)``."""
        return String(255)

    def validate(self, value: Any) -> Any:
        """Hash plaintext with the configured scheme, or pass an existing hash through.

        New values are hashed via :func:`~alchemiq.configure_password_hashing`'s
        current scheme (default scrypt).  A value that is already a stored hash of
        any supported scheme (e.g. rehydrated from the DB) is returned unchanged to
        avoid double-hashing.
        """
        s = str(value)
        if is_hashed(s):
            return s
        return hash_password(s)


def install_password_check(cls: type, fields: dict[str, Any]) -> None:
    """Inject check_password(raw) -> bool on *cls* if it has a Password field.

    Called by the model pipeline after register_validators.  v1 supports exactly
    one Password field per model; a second one raises ConfigError at class-definition
    time.
    """
    from alchemiq.exceptions import ConfigError

    password_fields = [name for name, field in fields.items() if isinstance(field, Password)]

    if len(password_fields) > 1:
        raise ConfigError(
            f"{cls.__name__} declares {len(password_fields)} Password fields "
            f"({', '.join(password_fields)}); only one Password field is allowed per model."
        )

    if not password_fields:
        return

    _fname = password_fields[0]

    def check_password(self: Any, raw: str) -> bool:
        stored = getattr(self, _fname)
        if stored is None:
            return False
        return verify_password(raw, stored)

    cls.check_password = check_password  # ty: ignore[unresolved-attribute]
