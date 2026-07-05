from alchemiq.model import Model
from alchemiq.outbox.models import OutboxEvent, is_outbox
from alchemiq.outbox.status import PENDING
from alchemiq.types import PK


class _Plain(Model):
    __tablename__ = "outbox_model_um_plain"
    id: PK[int]


class _Boxed(Model):
    __tablename__ = "outbox_model_um_boxed"
    id: PK[int]

    class Meta:
        outbox = True


def test_table_name_is_outbox():
    assert OutboxEvent.__tablename__ == "outbox"


def test_optional_columns_are_nullable():
    t = OutboxEvent.__table__
    for col in (
        "aggregate_type",
        "aggregate_id",
        "event_type",
        "headers",
        "published_at",
        "last_error",
    ):
        assert t.c[col].nullable is True, col


def test_required_columns_not_nullable():
    t = OutboxEvent.__table__
    for col in ("topic", "payload", "status"):
        assert t.c[col].nullable is False, col


def test_status_default_is_pending():
    assert OutboxEvent.__table__.c.status.default.arg == PENDING


def test_attempts_default_is_zero():
    assert OutboxEvent.__table__.c.attempts.default.arg == 0


def test_status_index_present():
    names = {ix.name for ix in OutboxEvent.__table__.indexes}
    assert "ix_outbox_status_id" in names


def test_is_outbox_true_for_flagged_model():
    assert is_outbox(_Boxed) is True


def test_is_outbox_false_for_plain_model():
    assert is_outbox(_Plain) is False


def test_is_outbox_false_for_bare_class():
    class _Bare:
        pass

    assert is_outbox(_Bare) is False
