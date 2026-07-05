from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from typing import Any, Literal

from alchemiq.exceptions import ConfigError

_N, _R, _P, _DKLEN = 2**14, 8, 1, 32

Scheme = Literal["scrypt", "argon2", "bcrypt"]
_VALID_SCHEMES: tuple[str, ...] = ("scrypt", "argon2", "bcrypt")
_SCRYPT_HASH_RE = re.compile(r"^scrypt\$[A-Za-z0-9+/]+=*\$[A-Za-z0-9+/]+=*$")
_BCRYPT_HASH_RE = re.compile(r"^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$")
_ARGON2_HASH_RE = re.compile(r"^\$argon2(id|i|d)\$v=\d+\$m=\d+,t=\d+,p=\d+\$[^$]+\$[^$]+$")

# Process-global scheme used for NEW hashes (verify always dispatches per-hash).
_scheme: str = "scrypt"


def _scrypt_hash(raw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(raw.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def _scrypt_verify(raw: str, stored: str) -> bool:
    try:
        scheme, b_salt, b_dk = stored.split("$", 2)
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    salt = base64.b64decode(b_salt)
    expected = base64.b64decode(b_dk)
    dk = hashlib.scrypt(raw.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=len(expected))
    return hmac.compare_digest(dk, expected)


def _argon2_hasher() -> Any:
    try:
        from argon2 import PasswordHasher  # ty: ignore[unresolved-import]
    except ImportError as e:
        raise ConfigError(
            "argon2 password hashing requires the [argon2] extra: pip install 'alchemiq[argon2]'"
        ) from e
    return PasswordHasher()


def _argon2_hash(raw: str) -> str:
    return _argon2_hasher().hash(raw)


def _argon2_verify(raw: str, stored: str) -> bool:
    hasher = _argon2_hasher()  # raises ConfigError if the extra is missing
    try:
        hasher.verify(stored, raw)
        return True
    except Exception:
        # argon2 raises VerifyMismatchError / InvalidHash on a bad password or
        # malformed stored hash - both mean "does not verify".
        return False


def _bcrypt_module() -> Any:
    try:
        import bcrypt  # ty: ignore[unresolved-import]
    except ImportError as e:
        raise ConfigError(
            "bcrypt password hashing requires the [bcrypt] extra: pip install 'alchemiq[bcrypt]'"
        ) from e
    return bcrypt


def _bcrypt_hash(raw: str) -> str:
    bcrypt = _bcrypt_module()
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()


def _bcrypt_verify(raw: str, stored: str) -> bool:
    bcrypt = _bcrypt_module()  # raises ConfigError if the extra is missing
    try:
        return bool(bcrypt.checkpw(raw.encode(), stored.encode()))
    except ValueError:
        return False


_HASHERS = {"scrypt": _scrypt_hash, "argon2": _argon2_hash, "bcrypt": _bcrypt_hash}


def hash_password(raw: str) -> str:
    """Hash plaintext with the currently configured scheme (default ``scrypt``)."""
    return _HASHERS[_scheme](raw)


def verify_password(raw: str, stored: str) -> bool:
    """Verify plaintext against a stored hash, dispatching on the hash's format.

    Raises :class:`.ConfigError` if the stored hash's backend extra is not
    installed - "cannot verify" is not the same as "wrong password".
    """
    if stored.startswith("$argon2"):
        return _argon2_verify(raw, stored)
    if stored.startswith(("$2a$", "$2b$", "$2y$")):
        return _bcrypt_verify(raw, stored)
    if stored.startswith("scrypt$"):
        return _scrypt_verify(raw, stored)
    return False


def is_hashed(value: str) -> bool:
    """Return ``True`` if *value* is already a hash produced by any known scheme."""
    return (
        bool(_ARGON2_HASH_RE.match(value))
        or bool(_BCRYPT_HASH_RE.match(value))
        or bool(_SCRYPT_HASH_RE.match(value))
    )


def configure_password_hashing(scheme: Scheme) -> None:
    """Set the process-global scheme used to hash new passwords.

    The default is ``scrypt`` (stdlib, no extra). ``argon2`` requires the
    ``[argon2]`` extra and ``bcrypt`` the ``[bcrypt]`` extra; the backend is
    checked eagerly so a misconfiguration fails at startup, not at first hash.
    Existing stored hashes keep verifying regardless - :func:`verify_password`
    dispatches on each hash's own format.

    :param scheme: one of ``"scrypt"``, ``"argon2"``, ``"bcrypt"``.
    :raises ConfigError: on an unknown scheme or a missing backend extra.
    """
    if scheme not in _VALID_SCHEMES:
        raise ConfigError(
            f"unknown password-hashing scheme {scheme!r}; choose one of {_VALID_SCHEMES}"
        )
    if scheme == "argon2":
        _argon2_hasher()
    elif scheme == "bcrypt":
        _bcrypt_module()
    global _scheme
    _scheme = scheme


def reset_password_hashing() -> None:
    """Restore the default ``scrypt`` scheme. Intended for tests and teardown."""
    global _scheme
    _scheme = "scrypt"
