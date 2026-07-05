from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from alchemiq.exceptions import ConfigError

_key_provider: Callable[[], bytes] | None = None


def set_key_provider(provider: Callable[[], bytes]) -> None:
    global _key_provider
    _key_provider = provider


def _key() -> bytes:
    if _key_provider is not None:
        return _key_provider()
    env = os.environ.get("ALCHEMIQ_ENCRYPTION_KEY")
    if env:
        import base64

        return base64.urlsafe_b64decode(env)
    raise ConfigError("No encryption key: set ALCHEMIQ_ENCRYPTION_KEY or call set_key_provider()")


def _aesgcm() -> Any:  # returns AESGCM class; typed as Any to avoid hard import
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # ty: ignore[unresolved-import]  # noqa: E501,I001
    except ImportError as e:
        raise ConfigError(
            "Encrypted requires the 'crypto' extra: pip install alchemiq[crypto]"
        ) from e
    return AESGCM


def encrypt(data: bytes) -> bytes:
    aesgcm: Any = _aesgcm()(_key())
    nonce = os.urandom(12)
    ct: bytes = aesgcm.encrypt(nonce, data, None)
    return nonce + ct


def decrypt(token: bytes) -> bytes:
    aesgcm: Any = _aesgcm()(_key())
    result: bytes = aesgcm.decrypt(token[:12], token[12:], None)
    return result
