import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from alchemiq import Model
from alchemiq.exceptions import ConfigError, ValidationError
from alchemiq.types import PK, URL, Password, Phone, Slug


class Page(Model):
    id: PK[int]
    slug: Slug
    link: URL
    phone: Phone
    secret: Password


def test_slug_normalizes_and_validates():
    p = Page()
    p.slug = "Hello-World"
    assert p.slug == "hello-world"
    with pytest.raises(ValidationError):
        p.slug = "bad slug!"


def test_url_validates():
    p = Page()
    p.link = "https://example.com/x"
    assert p.link.startswith("https://")
    with pytest.raises(ValidationError):
        p.link = "notaurl"


def test_phone_e164():
    p = Page()
    p.phone = "+14155552671"
    assert p.phone == "+14155552671"
    with pytest.raises(ValidationError):
        p.phone = "415"


def test_password_hashes_and_verifies():
    p = Page()
    p.secret = "s3cr3t"
    assert p.secret != "s3cr3t"  # stored as hash
    assert p.check_password("s3cr3t") is True
    assert p.check_password("wrong") is False


def test_password_raw_starting_with_scrypt_prefix_is_hashed():
    """A raw password that starts with 'scrypt$' but is NOT a valid full hash
    must be hashed, not passed through unchanged."""
    p = Page()
    p.secret = "scrypt$hunter2"
    assert p.secret != "scrypt$hunter2"  # must have been hashed
    assert p.check_password("scrypt$hunter2") is True


def test_password_genuine_hash_is_not_rehashed():
    """A value that is already a full scrypt hash (e.g. rehydrated from DB)
    must be passed through without double-hashing."""
    p = Page()
    p.secret = "s3cr3t"
    stored_hash = p.secret  # e.g. "scrypt$<b64salt>$<b64dk>"
    # Simulate rehydration: assign the stored hash back
    p.secret = stored_hash
    assert p.secret == stored_hash  # still the same hash, not re-hashed
    assert p.check_password("s3cr3t") is True


def test_check_password_raises_config_error_on_model_without_password_field():
    """Calling check_password on a model without a Password field raises ConfigError."""

    class NoPasswordModel(Model):
        __tablename__ = "np_no_password_model"
        id: PK[int]
        name: str

    instance = NoPasswordModel()
    with pytest.raises(ConfigError, match="no Password field"):
        instance.check_password("anything")


def test_check_password_typed_on_model_with_password_field():
    """check_password on a model WITH a Password field verifies correctly."""
    p = Page()
    p.secret = "mypassword"
    assert p.check_password("mypassword") is True
    assert p.check_password("wrongpassword") is False


def test_multiple_password_fields_raises_config_error():
    """Declaring two Password fields on a model raises ConfigError at class-definition time."""
    with pytest.raises(ConfigError, match="Password"):

        class TwoPasswords(Model):
            __tablename__ = "np_two_passwords"
            id: PK[int]
            pass1: Password
            pass2: Password


# A strategy for valid slug strings: lowercase ASCII alphanumeric segments joined by hyphens.
_slug_segment = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll", "Nd"),
        whitelist_characters="0123456789",
        # Restrict to ASCII (codepoints 0x61-0x7a for a-z, 0x30-0x39 for 0-9)
        max_codepoint=0x7E,
    ).filter(lambda c: c.isascii()),
    min_size=1,
    max_size=10,
)
_valid_slug_st = st.lists(_slug_segment, min_size=1, max_size=5).map("-".join)


@given(slug=_valid_slug_st)
@settings(max_examples=50)
def test_slug_hypothesis_valid_slugs_are_idempotent(slug):
    """Slug.validate is idempotent: already-valid lowercase slugs pass through unchanged."""
    s = Slug()
    result = s.validate(slug)
    assert result == slug.lower()
    # Second pass is idempotent
    assert s.validate(result) == result
