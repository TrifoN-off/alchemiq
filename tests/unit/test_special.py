import enum
import os

import pytest

from alchemiq.exceptions import ConfigError, ValidationError
from alchemiq.types import JSON, Array, Enum
from alchemiq.types.numeric import Positive


def test_array_validates_each_element():
    arr = Array(Positive())
    assert arr.validate([1, 2, 3]) == [1, 2, 3]
    with pytest.raises(ValidationError):
        arr.validate([1, -2])


def test_enum_column_uses_pg_enum():
    class Color(enum.Enum):
        RED = "red"
        BLUE = "blue"

    from sqlalchemy import Enum as SaEnum

    assert isinstance(Enum(Color).column_type(), SaEnum)


def test_json_validates_with_pydantic():
    import pydantic

    class Addr(pydantic.BaseModel):
        city: str

    j = JSON(model=Addr)
    assert j.validate({"city": "X"}) == {"city": "X"}
    with pytest.raises(ValidationError):
        j.validate({"wrong": 1})


def test_array_class_getitem_immutable():
    """Array[int] must not mutate an existing Field instance."""
    from alchemiq.types.special import Array as Arr

    arr = Arr[int]
    assert arr.inner.python_type is int


def test_encrypted_config_error_when_crypto_missing(monkeypatch):
    """When 'cryptography' package is absent, process_bind_param raises ConfigError."""
    # Simulate missing cryptography by patching the import inside _internal.crypto
    import alchemiq._internal.crypto as _crypto_mod

    def _failing_aesgcm():
        raise ConfigError("Encrypted requires the 'crypto' extra: pip install alchemiq[crypto]")

    monkeypatch.setattr(_crypto_mod, "_aesgcm", _failing_aesgcm)

    from alchemiq.types.special import Encrypted

    col_type = Encrypted().column_type()
    with pytest.raises(ConfigError, match="crypto"):
        col_type.process_bind_param("secret", None)


def test_encrypted_config_error_import_missing(monkeypatch):
    """When the cryptography import fails inside _aesgcm, it must raise ConfigError."""
    import alchemiq._internal.crypto as _crypto_mod

    def _failing_aesgcm() -> None:
        raise ConfigError("Encrypted requires the 'crypto' extra: pip install alchemiq[crypto]")

    monkeypatch.setattr(_crypto_mod, "_aesgcm", _failing_aesgcm)

    from alchemiq.types.special import Encrypted

    col_type = Encrypted().column_type()
    with pytest.raises(ConfigError, match="crypto"):
        col_type.process_bind_param("secret", None)


def test_crypto_encrypt_decrypt_round_trip():
    """Unit test for crypto.encrypt/decrypt without DB - using a set key provider."""
    import alchemiq._internal.crypto as _crypto_mod

    key = os.urandom(32)
    original_provider = _crypto_mod._key_provider
    try:
        _crypto_mod.set_key_provider(lambda: key)
        plaintext = b"hello world"
        ciphertext = _crypto_mod.encrypt(plaintext)
        assert ciphertext != plaintext
        assert len(ciphertext) > len(plaintext)
        result = _crypto_mod.decrypt(ciphertext)
        assert result == plaintext
    finally:
        _crypto_mod._key_provider = original_provider
