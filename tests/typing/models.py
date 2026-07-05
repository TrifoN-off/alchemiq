"""Consumer-side typing fixture - must be clean on ty + mypy + pyright.

NOT collected by pytest (no test_ prefix); checked statically by the acceptance
harness (test_typing_acceptance.py) and the CI 'typing' job. Imported only by the
static checkers, never at pytest runtime, so its models do not pollute metadata.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import assert_type

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from alchemiq import Model, OneToOne
from alchemiq.types import (
    JSON,
    PK,
    UUID4,
    Array,
    Date,
    DateTimeTz,
    Email,
    Encrypted,
    Enum,
    Maybe,
    Money,
    Nothing,
    Positive,
    Some,
    Time,
)


class Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


class TypingTag(Model):
    __tablename__ = "typing_tag"
    id: PK[int]
    name: str


class TypingProfile(Model):
    __tablename__ = "typing_profile"
    id: PK[int]
    bio: str


class Account(Model):
    __tablename__ = "typing_account"
    id: PK[int]
    email: Email
    name: str
    age: int
    price: Money
    score: Positive
    created: DateTimeTz
    uid: UUID4
    data: JSON
    tags: Array[int]
    secret: Encrypted[str]
    nick: Maybe[str]
    bio: str | None
    status: Enum[Color]
    day: Date
    moment: Time
    extra: Mapped[dict] = mapped_column(JSONB)
    related_tags: list[TypingTag]
    profile: OneToOne[TypingProfile]


def _reads(a: Account) -> None:
    assert_type(a.id, int)
    assert_type(a.email, str)
    assert_type(a.name, str)
    assert_type(a.age, int)
    assert_type(a.price, Decimal)
    assert_type(a.score, int)
    assert_type(a.created, datetime)
    assert_type(a.uid, uuid.UUID)
    assert_type(a.data, dict)
    assert_type(a.tags, list[int])
    assert_type(a.secret, str)
    assert_type(a.nick, Maybe[str])
    assert_type(a.bio, str | None)
    assert_type(a.status, Color)
    assert_type(a.day, date)
    assert_type(a.moment, time)
    assert_type(a.extra, dict)
    assert_type(a.related_tags, list[TypingTag])
    assert_type(a.profile, TypingProfile)


def _writes(a: Account) -> None:
    a.email = "user@example.com"
    a.name = "Ada"
    a.age = 30
    a.price = Decimal("9.99")
    a.score = 5
    a.uid = uuid.uuid4()
    a.data = {"k": "v"}
    a.tags = [1, 2, 3]
    a.secret = "s3cret"
    a.nick = Some("nick")
    a.nick = Nothing
    a.bio = "hello"
    a.bio = None
    a.status = Color.BLUE
    a.day = date(2026, 6, 26)
    a.moment = time(12, 0)
