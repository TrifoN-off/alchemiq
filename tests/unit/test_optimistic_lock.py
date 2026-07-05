from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger
from sqlalchemy import inspect as sa_inspect

from alchemiq import ConcurrentModificationError, Model
from alchemiq.exceptions import ConfigError, PersistenceError
from alchemiq.query.soft_delete import is_versioned
from alchemiq.repository.base import _assert_version
from alchemiq.types import PK
from alchemiq.types.numeric import Version

pytestmark = pytest.mark.unit


class _Versioned(Model):
    __tablename__ = "lock_unit_versioned"
    id: PK[int]
    name: str

    class Meta:
        versioned = True


class _Plain(Model):
    __tablename__ = "lock_unit_plain"
    id: PK[int]
    name: str


class _BusinessVersion(Model):
    __tablename__ = "lock_unit_business_version"
    id: PK[int]
    version: int  # user's own business field - must coexist, untouched
    name: str

    class Meta:
        versioned = True


def test_meta_versioned_parsed() -> None:
    assert _Versioned.__alchemiq_meta__.versioned is True
    assert _Plain.__alchemiq_meta__.versioned is False


def test_version_column_injected() -> None:
    assert "_version" in _Versioned.__alchemiq_fields__
    assert isinstance(_Versioned.__alchemiq_fields__["_version"], Version)


def test_version_column_is_bigint_not_null() -> None:
    col = _Versioned.__table__.c._version
    assert isinstance(col.type, BigInteger)
    assert col.nullable is False
    assert col.server_default is not None
    assert col.server_default.arg.text == "1"


def test_version_not_injected_when_not_versioned() -> None:
    assert "_version" not in _Plain.__alchemiq_fields__


def test_business_version_field_coexists() -> None:
    # user's `version` stays a plain field; the lock counter is the separate `_version`
    assert "version" in _BusinessVersion.__alchemiq_fields__
    assert "_version" in _BusinessVersion.__alchemiq_fields__
    assert not isinstance(_BusinessVersion.__alchemiq_fields__["version"], Version)
    assert isinstance(_BusinessVersion.__alchemiq_fields__["_version"], Version)
    assert sa_inspect(_BusinessVersion).version_id_col is _BusinessVersion.__table__.c._version


class _WithMapperArgs(Model):
    __tablename__ = "lock_unit_mapper_args"
    __mapper_args__ = {"eager_defaults": True}
    id: PK[int]
    name: str

    class Meta:
        versioned = True


def test_version_id_col_wired() -> None:
    assert sa_inspect(_Versioned).version_id_col is _Versioned.__table__.c._version


def test_version_id_col_absent_when_not_versioned() -> None:
    assert sa_inspect(_Plain).version_id_col is None


def test_mapper_args_merge_preserves_existing() -> None:
    assert _WithMapperArgs.__mapper_args__["eager_defaults"] is True
    assert sa_inspect(_WithMapperArgs).version_id_col is _WithMapperArgs.__table__.c._version


def test_concurrent_error_is_persistence_error() -> None:
    assert issubclass(ConcurrentModificationError, PersistenceError)


def test_is_versioned() -> None:
    assert is_versioned(_Versioned) is True
    assert is_versioned(_Plain) is False


def test_assert_version_non_versioned_raises_config_error() -> None:
    with pytest.raises(ConfigError):
        _assert_version(_Plain, SimpleNamespace(_version=1), 1, pk=1)


def test_assert_version_mismatch_raises_concurrent() -> None:
    with pytest.raises(ConcurrentModificationError):
        _assert_version(_Versioned, SimpleNamespace(_version=2), 1, pk=1)


def test_assert_version_match_ok() -> None:
    _assert_version(_Versioned, SimpleNamespace(_version=1), 1, pk=1)  # no raise


def test_version_of_non_versioned_raises() -> None:
    from alchemiq.query.soft_delete import version_of

    with pytest.raises(ConfigError):
        version_of(_Plain(id=1, name="x"))


def test_concurrent_error_exported() -> None:
    import alchemiq

    assert alchemiq.ConcurrentModificationError is ConcurrentModificationError
    assert "ConcurrentModificationError" in alchemiq.__all__


def test_status_for_concurrent_is_409() -> None:
    from alchemiq.fastapi.errors import status_for

    assert status_for(ConcurrentModificationError("x")) == 409
