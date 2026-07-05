import pytest

from alchemiq import ForeignKey, Model
from alchemiq.exceptions import DisallowedFieldError
from alchemiq.query import Q
from alchemiq.types import PK


class Writer(Model):
    id: PK[int]
    name: str


class Post(Model):
    id: PK[int]
    title: str
    writer: Writer = ForeignKey(related_name="posts")


def test_traversal_denied_by_default():
    payload = [0, 0, [["writer__name", "neo"]]]
    with pytest.raises(DisallowedFieldError):
        Q.from_data(payload, model=Post)


def test_traversal_allowed_when_whitelisted():
    q = Q(writer__name__icontains="neo")
    restored = Q.from_data(q.to_data(), model=Post, allow={"writer__name"})
    assert restored == q


def test_own_column_still_allowed_by_default():
    q = Q(title="hello")
    assert Q.from_data(q.to_data(), model=Post) == q


def test_deny_beats_allow_on_traversal():
    q = Q(writer__name="neo")
    with pytest.raises(DisallowedFieldError):
        Q.from_data(q.to_data(), model=Post, allow={"writer__name"}, deny={"writer__name"})


def test_bogus_relation_in_allow_is_rejected():
    payload = [0, 0, [["ghost__name", "x"]]]
    with pytest.raises(DisallowedFieldError):
        Q.from_data(payload, model=Post, allow={"ghost__name"})
