"""Models for the SQLite dev/test tier suite.

Suite tables use the ``sq_`` name prefix so the conftest fixture can create
exactly this suite's tables - the process-global metadata also carries every
PG/CH test model, some of which use PostgreSQL-only column types.  Models that
must be registered but NEVER created by the fixture (loud-refusal tests) use
the ``sqnope_`` prefix.
"""

from __future__ import annotations

import enum

from alchemiq import ForeignKey, Model, OneToOne
from alchemiq.types import JSON, PK, UUID4, UUID7, Array, DateTimeTz, Enum, Field, Maybe


class SqAuthor(Model):
    __tablename__ = "sq_author"
    id: PK[int]
    name: str


class SqBook(Model):
    __tablename__ = "sq_book"
    id: PK[int]
    title: str
    author: SqAuthor = ForeignKey(related_name="books")  # type: ignore[assignment]


class SqColor(enum.Enum):
    red = "red"
    blue = "blue"


class SqKitchen(Model):
    __tablename__ = "sq_kitchen"
    id: PK[int]
    ref4: UUID4
    ref7: UUID7
    payload: JSON
    meta: Maybe[JSON]
    color: Enum[SqColor]
    seen_at: DateTimeTz

    class Meta:
        timestamps = True


class SqnopeArrayed(Model):
    __tablename__ = "sqnope_arrayed"
    id: PK[int]
    tags: Array[int]


class SqUpsertItem(Model):
    __tablename__ = "sq_upsert_item"
    id: PK[int]
    sku: str = Field(unique=True)  # type: ignore[assignment]
    qty: int


class SqNote(Model):
    __tablename__ = "sq_note"
    id: PK[int]
    title: str
    rank: int


class SqSoft(Model):
    __tablename__ = "sq_soft"
    id: PK[int]
    name: str

    class Meta:
        soft_delete = True


class SqVersioned(Model):
    __tablename__ = "sq_versioned"
    id: PK[int]
    name: str

    class Meta:
        versioned = True


class SqSignal(Model):
    __tablename__ = "sq_signal"
    id: PK[int]
    name: str


class SqProfile(Model):
    __tablename__ = "sq_profile"
    id: PK[int]
    bio: str


class SqUser(Model):
    __tablename__ = "sq_user"
    id: PK[int]
    profile: OneToOne[SqProfile]


class SqTag(Model):
    __tablename__ = "sq_tag"
    id: PK[int]
    name: str


class SqPost(Model):
    __tablename__ = "sq_post"
    id: PK[int]
    title: str
    tags: list[SqTag]


class SqOrder(Model):
    __tablename__ = "sq_order"
    id: PK[int]
    total: int

    class Meta:
        outbox = True
