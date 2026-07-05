"""Integration tests: DDL + round-trip data persistence through real PostgreSQL.

Each test class uses models declared once at module level (table names are unique
to this module). The session fixture creates/drops all tables in metadata per test.
"""

from __future__ import annotations

import enum
import os
import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text

from alchemiq import Model
from alchemiq._internal import crypto as _crypto
from alchemiq.types import PK
from alchemiq.types.base import Field
from alchemiq.types.maybe import MaybeField, Nothing, Some
from alchemiq.types.numeric import Money
from alchemiq.types.pk import UUID4
from alchemiq.types.special import JSON, Array, Encrypted
from alchemiq.types.special import Enum as AlchemiqEnum
from alchemiq.types.strings import Email

# ---------------------------------------------------------------------------
# Model declarations (module-level so SQLAlchemy registers them exactly once)
# ---------------------------------------------------------------------------


class Ledger(Model):
    """Model for test_money_and_email."""

    __tablename__ = "it_ledger"

    id: PK[int]
    email: Email
    balance: Money


class NullableRecord(Model):
    """Model for test_maybe_some_nothing."""

    __tablename__ = "it_nullable_record"

    id: PK[int]
    note: MaybeField = MaybeField(Field(python_type=str))  # type: ignore[assignment]


class SecretRecord(Model):
    """Model for test_encrypted_roundtrip."""

    __tablename__ = "it_secret_record"

    id: PK[int]
    payload: Encrypted


class Color(enum.Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


class PgTypesRecord(Model):
    """Model for test_pg_types_roundtrip - UUID4 PK, Array, Enum, JSON."""

    __tablename__ = "it_pg_types"

    id: UUID4 = UUID4(primary_key=True)
    tags: Array[int]
    color: AlchemiqEnum[Color]
    meta: JSON


class EmailRecord(Model):
    """Model for test_load_bypasses_validation - verifies ORM load skips eager validation."""

    __tablename__ = "it_email_record"

    id: PK[int]
    email: Email


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_money_and_email(session: Any) -> None:
    """Money stored as integer minor-units, Email normalized to lowercase."""
    row = Ledger(email="User@Example.COM", balance=Decimal("99.99"))
    session.add(row)
    await session.commit()
    session.expire_all()

    result = await session.execute(select(Ledger))
    loaded: Ledger = result.scalars().one()

    assert loaded.email == "user@example.com", "Email must be lowercased"
    assert loaded.balance == Decimal("99.99"), "Balance must survive round-trip exactly"
    # Confirm balance is stored as integer cents in the raw column
    raw = await session.execute(text("SELECT balance FROM it_ledger"))
    raw_val = raw.scalar_one()
    assert raw_val == 9999, f"Expected raw int 9999, got {raw_val!r}"


@pytest.mark.integration
async def test_maybe_some_nothing(session: Any) -> None:
    """Maybe[str]: Some persists and reloads; Nothing persists as NULL and reloads as Nothing."""
    some_row = NullableRecord(note=Some("hello"))
    nothing_row = NullableRecord(note=Nothing)
    session.add_all([some_row, nothing_row])
    await session.commit()
    session.expire_all()

    result = await session.execute(select(NullableRecord).order_by(NullableRecord.id))
    rows = result.scalars().all()
    assert len(rows) == 2

    # First row: Some("hello")
    assert isinstance(rows[0].note, Some), f"Expected Some, got {rows[0].note!r}"
    assert rows[0].note.unwrap() == "hello"

    # Second row: Nothing
    assert rows[1].note is Nothing, f"Expected Nothing, got {rows[1].note!r}"

    # Verify NULL in DB directly
    raw = await session.execute(text("SELECT note FROM it_nullable_record ORDER BY id"))
    db_values = [r[0] for r in raw.fetchall()]
    assert db_values[0] == "hello", f"Expected 'hello' in DB, got {db_values[0]!r}"
    assert db_values[1] is None, f"Expected NULL in DB, got {db_values[1]!r}"


@pytest.mark.integration
async def test_encrypted_roundtrip(session: Any) -> None:
    """Encrypted field: raw DB value is ciphertext; ORM decrypts back to plaintext."""
    plaintext = "super-secret-value"
    key_bytes = os.urandom(32)
    _crypto.set_key_provider(lambda: key_bytes)

    try:
        row = SecretRecord(payload=plaintext)
        session.add(row)
        await session.commit()
        row_id = row.id
        session.expire_all()

        # Assert raw DB column is NOT the plaintext (it's binary ciphertext).
        raw = await session.execute(
            text("SELECT payload FROM it_secret_record WHERE id = :id"),
            {"id": row_id},
        )
        raw_bytes: bytes = raw.scalar_one()
        assert isinstance(raw_bytes, (bytes, memoryview)), (
            f"Expected bytes at rest, got {type(raw_bytes)}"
        )
        raw_bytes = bytes(raw_bytes)
        assert plaintext.encode() not in raw_bytes, "Plaintext must NOT appear in raw ciphertext"
        assert len(raw_bytes) > len(plaintext), "Ciphertext must be longer than plaintext"

        # ORM reload decrypts back.
        result = await session.execute(select(SecretRecord).where(SecretRecord.id == row_id))
        loaded: SecretRecord = result.scalars().one()
        assert loaded.payload == plaintext, (
            f"ORM must decrypt to original plaintext, got {loaded.payload!r}"
        )
    finally:
        # Reset key provider so other tests are not affected.
        _crypto._key_provider = None


@pytest.mark.integration
async def test_load_bypasses_validation(session: Any) -> None:
    """ORM hydration must NOT re-run eager validators on loaded rows.

    Inserts a row via raw SQL with a value that would FAIL Email.validate()
    if re-validated on load (non-normalized uppercase email).  Then loads the
    row through the ORM and asserts:
    - No ValidationError is raised during load.
    - The value is returned exactly as stored (not re-normalized).

    This locks the invariant that the SQLAlchemy ``set`` event fires only on
    explicit attribute assignment, never during ORM result hydration.
    """
    # Insert a value that WOULD fail Email validation if re-validated:
    # uppercase letters violate the normalisation contract (Email.validate lowercases).
    invalid_for_validator = "NOT@Normalized.COM"
    await session.execute(
        text("INSERT INTO it_email_record (email) VALUES (:email)"),
        {"email": invalid_for_validator},
    )
    await session.commit()
    session.expire_all()

    # Loading must succeed without raising ValidationError.
    result = await session.execute(select(EmailRecord))
    loaded: EmailRecord = result.scalars().one()

    # Value must be returned exactly as stored - no re-normalization on load.
    assert loaded.email == invalid_for_validator, (
        f"ORM hydration must not re-validate/re-normalize; expected {invalid_for_validator!r}, "
        f"got {loaded.email!r}"
    )


@pytest.mark.integration
async def test_pg_types_roundtrip(session: Any) -> None:
    """UUID4 PK, Array[int], Enum, JSONB all round-trip through Postgres."""
    row = PgTypesRecord(
        tags=[1, 2, 3],
        color=Color.GREEN,
        meta={"version": 1, "labels": ["a", "b"]},
    )
    session.add(row)
    await session.commit()
    stored_id: uuid.UUID = row.id
    session.expire_all()

    result = await session.execute(select(PgTypesRecord).where(PgTypesRecord.id == stored_id))
    loaded: PgTypesRecord = result.scalars().one()

    assert isinstance(loaded.id, uuid.UUID), "PK must be a UUID"
    assert loaded.id == stored_id, "UUID PK must survive round-trip"
    assert loaded.tags == [1, 2, 3], f"Array must survive round-trip, got {loaded.tags!r}"
    assert loaded.color == Color.GREEN, f"Enum must survive round-trip, got {loaded.color!r}"
    assert loaded.meta == {"version": 1, "labels": ["a", "b"]}, (
        f"JSON must survive round-trip, got {loaded.meta!r}"
    )
