import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal

from alchemiq._internal.wire import decode_scalar, encode_scalar


def test_plain_json_natives_roundtrip():
    for v, t in [("hi", str), (5, int), (1.5, float), (True, bool)]:
        assert encode_scalar(v) == v
        assert decode_scalar(encode_scalar(v), t) == v


def test_decimal_roundtrip():
    v = Decimal("12.50")
    enc = encode_scalar(v)
    assert enc == "12.50"
    assert decode_scalar(enc, Decimal) == v


def test_datetime_tz_roundtrip():
    v = datetime(2026, 6, 24, 10, 30, tzinfo=UTC)
    enc = encode_scalar(v)
    assert isinstance(enc, str)
    assert decode_scalar(enc, datetime) == v


def test_date_and_time_roundtrip():
    assert decode_scalar(encode_scalar(date(2026, 6, 24)), date) == date(2026, 6, 24)
    assert decode_scalar(encode_scalar(time(10, 30)), time) == time(10, 30)


def test_uuid_roundtrip():
    v = uuid.uuid4()
    assert decode_scalar(encode_scalar(v), uuid.UUID) == v


def test_bytes_roundtrip():
    v = b"\x00\x01\x02"
    enc = encode_scalar(v)
    assert isinstance(enc, str)
    assert decode_scalar(enc, bytes) == v
