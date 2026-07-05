import pytest

from alchemiq import Model
from alchemiq.exceptions import DeserializationError
from alchemiq.query import Q
from alchemiq.types import PK


class WireRow(Model):
    id: PK[int]
    name: str


def test_bytes_roundtrip():
    q = Q(name__icontains="neo")
    assert Q.from_bytes(q.to_bytes(), model=WireRow) == q


def test_base64_roundtrip():
    q = Q(name="neo") | Q(id__gte=3)
    s = q.to_base64()
    assert isinstance(s, str)
    assert Q.from_base64(s, model=WireRow) == q


def test_malformed_base64_raises():
    with pytest.raises(DeserializationError):
        Q.from_base64("!!!not-base64!!!", model=WireRow)
