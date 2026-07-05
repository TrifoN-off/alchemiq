import datetime as dt

import pytest

from alchemiq import Model
from alchemiq.exceptions import ValidationError
from alchemiq.types import PK, CreatedAt, DateTimeTz, UpdatedAt
from alchemiq.types.temporal import EpochInt, UnixTimestamp


class Event(Model):
    id: PK[int]
    happened: DateTimeTz
    created_at: CreatedAt
    updated_at: UpdatedAt


def test_datetimetz_rejects_naive():
    with pytest.raises(ValidationError):
        DateTimeTz().validate(dt.datetime(2020, 1, 1))  # naive
    aware = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
    assert DateTimeTz().validate(aware) == aware


def test_unix_roundtrip():
    deco = EpochInt()
    aware = dt.datetime(2021, 1, 1, tzinfo=dt.UTC)
    epoch = deco.process_bind_param(aware, dialect=None)
    assert isinstance(epoch, int)
    assert deco.process_result_value(epoch, dialect=None) == aware


def test_updated_at_has_onupdate():
    assert Event.__table__.c.updated_at.onupdate is not None


def test_unix_timestamp_rejects_naive_datetime():
    """UnixTimestamp.validate must raise ValidationError for naive (tz-less) datetimes."""
    field = UnixTimestamp()
    naive = dt.datetime(2024, 1, 1)  # no tzinfo
    with pytest.raises(ValidationError, match="timezone-aware"):
        field.validate(naive)


def test_unix_timestamp_accepts_aware_datetime():
    """UnixTimestamp.validate must accept timezone-aware datetimes."""
    field = UnixTimestamp()
    aware = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert field.validate(aware) == aware
