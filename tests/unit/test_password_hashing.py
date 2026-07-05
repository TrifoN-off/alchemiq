from __future__ import annotations

import sys

import pytest

from alchemiq import Model
from alchemiq._internal.hashing import (
    configure_password_hashing,
    hash_password,
    is_hashed,
    reset_password_hashing,
    verify_password,
)
from alchemiq.exceptions import ConfigError
from alchemiq.types import PK, Password

pytestmark = pytest.mark.unit


# Models must be defined at module level so the metaclass can resolve annotations.


class _PwUserScrypt(Model):
    id: PK[int]
    secret: Password


class _PwUserArgon(Model):
    id: PK[int]
    secret: Password


class _PwUserPass(Model):
    id: PK[int]
    secret: Password


@pytest.fixture(autouse=True)
def _reset_scheme():
    yield
    reset_password_hashing()


@pytest.mark.parametrize("scheme", ["scrypt", "argon2", "bcrypt"])
def test_round_trip(scheme: str) -> None:
    configure_password_hashing(scheme)  # type: ignore[arg-type]
    h = hash_password("s3cr3t")
    assert h != "s3cr3t"
    assert verify_password("s3cr3t", h) is True
    assert verify_password("wrong", h) is False


@pytest.mark.parametrize(
    "scheme,prefix",
    [("scrypt", "scrypt$"), ("argon2", "$argon2"), ("bcrypt", "$2b$")],
)
def test_hash_has_scheme_prefix(scheme: str, prefix: str) -> None:
    configure_password_hashing(scheme)  # type: ignore[arg-type]
    assert hash_password("pw").startswith(prefix)


def test_verify_dispatches_across_schemes_regardless_of_current() -> None:
    configure_password_hashing("argon2")
    a = hash_password("pw")
    configure_password_hashing("bcrypt")
    b = hash_password("pw")
    configure_password_hashing("scrypt")
    s = hash_password("pw")
    # current scheme is scrypt, but verify works for every stored scheme by prefix
    assert verify_password("pw", a) is True
    assert verify_password("pw", b) is True
    assert verify_password("pw", s) is True


@pytest.mark.parametrize("scheme", ["scrypt", "argon2", "bcrypt"])
def test_is_hashed_true_for_each_scheme(scheme: str) -> None:
    configure_password_hashing(scheme)  # type: ignore[arg-type]
    assert is_hashed(hash_password("pw")) is True


def test_is_hashed_false_for_plaintext() -> None:
    assert is_hashed("s3cr3t") is False
    assert is_hashed("scrypt$incomplete") is False  # not the full scrypt format


def test_unknown_scheme_raises() -> None:
    with pytest.raises(ConfigError):
        configure_password_hashing("md5")  # type: ignore[arg-type]


def test_reset_restores_scrypt() -> None:
    configure_password_hashing("argon2")
    reset_password_hashing()
    assert hash_password("pw").startswith("scrypt$")


def test_verify_unrecognized_returns_false() -> None:
    assert verify_password("pw", "not-a-known-hash") is False


def test_missing_backend_raises_configerror(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force `import argon2` to fail even though the extra is installed in dev.
    monkeypatch.setitem(sys.modules, "argon2", None)
    with pytest.raises(ConfigError):
        configure_password_hashing("argon2")
    # verify on an argon2 hash without the backend RAISES (not False):
    with pytest.raises(ConfigError):
        verify_password("pw", "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA")


def test_public_surface_exports() -> None:
    import alchemiq

    assert hasattr(alchemiq, "configure_password_hashing")
    assert hasattr(alchemiq, "reset_password_hashing")
    assert "configure_password_hashing" in alchemiq.__all__
    assert "reset_password_hashing" in alchemiq.__all__


def test_password_field_hashes_on_assignment_default_scrypt() -> None:
    u = _PwUserScrypt(id=1, secret="s3cr3t")
    assert u.secret.startswith("scrypt$")
    assert u.check_password("s3cr3t") is True
    assert u.check_password("nope") is False


def test_password_field_respects_configured_scheme() -> None:
    import alchemiq

    alchemiq.configure_password_hashing("argon2")

    u = _PwUserArgon(id=1, secret="s3cr3t")
    assert u.secret.startswith("$argon2")
    assert u.check_password("s3cr3t") is True


def test_password_field_passthrough_does_not_double_hash() -> None:
    u = _PwUserPass(id=1, secret="s3cr3t")
    once = u.secret
    u.secret = once  # re-assigning an already-stored hash must not re-hash
    assert u.secret == once


@pytest.mark.parametrize(
    "plaintext",
    ["$2b$pancakes", "$2a$short", "$2y$nope", "$argon2pancake", "$argon2id-not-real"],
)
def test_is_hashed_false_for_plaintext_with_scheme_prefix(plaintext: str) -> None:
    assert is_hashed(plaintext) is False
