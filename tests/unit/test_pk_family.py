import uuid

from alchemiq._internal.ids import nanoid, uuid7
from alchemiq.types import UUID4, NanoID


def test_uuid7_is_time_sortable():
    a = uuid7()
    b = uuid7()
    assert a.version == 7
    assert str(a) < str(b)  # monotonic within a process


def test_uuid7_variant_bits():
    """RFC 9562 §5.7: variant bits must be 10xx (i.e. clock_seq_hi_variant & 0xC0 == 0x80)."""
    u = uuid7()
    # uuid.UUID exposes clock_seq_hi_variant as the high byte of the variant field.
    assert (u.clock_seq_hi_variant & 0xC0) == 0x80, (
        f"Expected RFC 4122 variant bits 10xx, got {u.clock_seq_hi_variant:#04x}"
    )


def test_nanoid_length_and_alphabet():
    nid = nanoid()
    assert len(nid) == 21
    assert all(c in "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_" for c in nid)


def test_uuid4_default_factory_produces_uuid():
    f = UUID4()
    val = f.config.default()  # default is a callable factory
    assert isinstance(val, uuid.UUID)
    assert val.version == 4


def test_nanoid_field_column_is_string():
    from sqlalchemy import String

    assert isinstance(NanoID().column_type(), String)
