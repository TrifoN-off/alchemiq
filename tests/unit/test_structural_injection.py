from __future__ import annotations

import pytest

from alchemiq import Model
from alchemiq.exceptions import ConfigError
from alchemiq.types import PK
from alchemiq.types.temporal import DateTimeTz

pytestmark = pytest.mark.unit


def test_created_at_collision_with_timestamps_raises() -> None:
    with pytest.raises(ConfigError):

        class _M(Model):
            __tablename__ = "structural_created_at"
            id: PK[int]
            created_at: DateTimeTz

            class Meta:
                timestamps = True


def test_updated_at_collision_with_timestamps_raises() -> None:
    with pytest.raises(ConfigError):

        class _M(Model):
            __tablename__ = "structural_updated_at"
            id: PK[int]
            updated_at: DateTimeTz

            class Meta:
                timestamps = True


def test_deleted_at_collision_with_soft_delete_raises() -> None:
    with pytest.raises(ConfigError):

        class _M(Model):
            __tablename__ = "structural_deleted_at"
            id: PK[int]
            deleted_at: DateTimeTz

            class Meta:
                soft_delete = True


def test_version_collision_with_versioned_raises() -> None:
    with pytest.raises(ConfigError):

        class _M(Model):
            __tablename__ = "structural_version"
            id: PK[int]
            _version: int

            class Meta:
                versioned = True


def test_structural_name_without_flag_is_a_normal_user_column() -> None:
    # `deleted_at` WITHOUT Meta.soft_delete is a plain user column - no error, no magic
    class _M(Model):
        __tablename__ = "structural_deleted_at_no_flag"
        id: PK[int]
        deleted_at: DateTimeTz

    assert "deleted_at" in _M.__alchemiq_fields__
