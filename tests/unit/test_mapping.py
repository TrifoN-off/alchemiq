from sqlalchemy import BigInteger, String

from alchemiq import Field, Model
from alchemiq.types import PK


class User(Model):
    id: PK[int]
    name: str
    nickname: str | None
    bio: str = Field(max_length=200)


def test_tablename_is_snake_case():
    assert User.__tablename__ == "user"


def test_primary_key_column():
    col = User.__table__.c.id
    assert col.primary_key is True
    assert isinstance(col.type, BigInteger)


def test_plain_and_optional_columns():
    assert User.__table__.c.name.nullable is False
    assert User.__table__.c.nickname.nullable is True


def test_field_config_applied():
    bio = User.__table__.c.bio
    assert isinstance(bio.type, String)
    assert bio.type.length == 200


def test_fields_registry_present():
    assert set(User.__alchemiq_fields__) == {"id", "name", "nickname", "bio"}
