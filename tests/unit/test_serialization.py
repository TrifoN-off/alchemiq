import datetime as dt

import pytest
from pydantic import BaseModel

from alchemiq import Model
from alchemiq.exceptions import ValidationError
from alchemiq.types import PK, DateTimeTz, Email, Maybe, Password

pytestmark = pytest.mark.unit


class SerAccount(Model):
    __tablename__ = "ser_account"
    id: PK[int]
    email: Email
    password: Password
    created: DateTimeTz


def _make() -> SerAccount:
    return SerAccount(
        id=1,
        email="A@B.com",
        password="secret",
        created=dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC),
    )


def test_to_dict_omits_password_by_default():
    d = _make().to_dict()
    assert "password" not in d
    assert d["email"] == "a@b.com"  # normalization preserved
    assert d["id"] == 1


def test_to_dict_python_mode_keeps_native_types():
    d = _make().to_dict()
    assert isinstance(d["created"], dt.datetime)


def test_to_dict_json_mode_isoformats():
    d = _make().to_dict(mode="json")
    assert d["created"] == "2026-01-02T03:04:05+00:00"


def test_include_is_a_whitelist():
    d = _make().to_dict(include={"id", "email"})
    assert set(d) == {"id", "email"}


def test_exclude_subtracts():
    d = _make().to_dict(exclude={"created"})
    assert "created" not in d and "email" in d


def test_password_surfaced_only_when_explicitly_included():
    d = _make().to_dict(include={"id", "password"})
    assert d["password"].startswith("scrypt$")  # the stored hash, opt-in only


def test_from_dict_constructs_and_validates():
    acc = SerAccount.from_dict(
        {
            "id": 9,
            "email": "X@Y.com",
            "password": "pw",
            "created": dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
        }
    )
    assert acc.id == 9
    assert acc.email == "x@y.com"  # normalized on assignment
    assert acc.check_password("pw")  # password hashed on assignment


def test_from_dict_rejects_unknown_keys():
    with pytest.raises(ValidationError) as exc_info:
        SerAccount.from_dict({"id": 1, "nope": "x"})
    err = exc_info.value
    assert err.model == "SerAccount"
    assert "nope" in err.reason


def test_from_dict_roundtrip_from_to_dict():
    original = _make()
    clone = SerAccount.from_dict(original.to_dict(include={"id", "email", "created"}))
    assert clone.to_dict(include={"id", "email"}) == {"id": 1, "email": "a@b.com"}


def test_to_schema_is_cached_basemodel_subclass():
    s1 = SerAccount.to_schema()
    s2 = SerAccount.to_schema()
    assert issubclass(s1, BaseModel)
    assert s1 is s2  # cached


def test_to_schema_omits_password():
    fields = SerAccount.to_schema().model_fields
    assert "password" not in fields
    assert {"id", "email", "created"} <= set(fields)


def test_to_pydantic_returns_instance():
    dto = _make().to_pydantic()
    assert isinstance(dto, BaseModel)
    assert dto.email == "a@b.com"
    assert not hasattr(dto, "password")


def test_to_schema_exclude_shapes_fields():
    fields = SerAccount.to_schema(exclude={"created"}).model_fields
    assert "created" not in fields and "email" in fields


def test_jsonify_unwraps_some():
    from alchemiq.model.serialization import _jsonify
    from alchemiq.types import Some

    assert _jsonify(Some("x")) == "x"


def test_jsonify_nothing_becomes_none():
    from alchemiq.model.serialization import _jsonify
    from alchemiq.types import Nothing

    assert _jsonify(Nothing) is None


def test_jsonify_recurses_into_some():
    import datetime as dt

    from alchemiq.model.serialization import _jsonify
    from alchemiq.types import Some

    assert _jsonify(Some(dt.date(2026, 6, 25))) == "2026-06-25"


def test_jsonify_json_mode_conversions():
    import enum
    from decimal import Decimal
    from uuid import UUID

    from alchemiq.model.serialization import _jsonify

    class _Color(enum.Enum):
        RED = "red"

    assert _jsonify(Decimal("1.50")) == "1.50"  # Decimal -> str
    assert _jsonify(UUID(int=0)) == "00000000-0000-0000-0000-000000000000"  # UUID -> str
    assert _jsonify(_Color.RED) == "red"  # Enum -> .value
    assert _jsonify(7) == 7  # non-special value passes through unchanged


class SerMaybeRow(Model):
    __tablename__ = "ser_maybe_row"
    id: PK[int]
    nickname: Maybe[str]


def test_to_dict_python_mode_unwraps_some():
    from alchemiq.types import Some

    row = SerMaybeRow(id=1, nickname="neo")
    assert row.nickname == Some("neo")  # stored wrapped
    d = row.to_dict()  # default mode="python"
    assert d["nickname"] == "neo"  # unwrapped, NOT Some("neo")


def test_to_dict_python_mode_nothing_becomes_none():
    from alchemiq.types import Nothing

    row = SerMaybeRow(id=2, nickname=Nothing)
    d = row.to_dict()
    assert d["nickname"] is None


def test_to_pydantic_unwraps_maybe():
    dto = SerMaybeRow(id=3, nickname="trinity").to_pydantic()
    assert dto.nickname == "trinity"  # plain str on the DTO, not Some(...)


class SerNullable(Model):
    __tablename__ = "ser_nullable_schema_row"
    id: PK[int]
    note: str | None


def test_build_schema_includes_password_when_explicit():
    from alchemiq.model.serialization import build_schema

    fields = build_schema(SerAccount, include={"id", "password"}).model_fields
    assert "password" in fields


def test_build_schema_nullable_field_is_optional():
    from alchemiq.model.serialization import build_schema

    fields = build_schema(SerNullable).model_fields
    assert not fields["note"].is_required()
