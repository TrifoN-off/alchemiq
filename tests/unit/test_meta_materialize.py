from alchemiq import Model
from alchemiq.model.meta_options import Check, Index
from alchemiq.types import PK, Money


class Order(Model):
    id: PK[int]
    total: Money

    class Meta:
        soft_delete = True
        timestamps = True
        indexes = [Index("total")]
        constraints = [Check("total >= 0")]


class Invoice(Model):
    """Model whose Meta.table_name overrides the snake_case default."""

    id: PK[int]

    class Meta:
        table_name = "custom_table"


def test_soft_delete_column():
    assert "deleted_at" in Order.__table__.c
    assert Order.__table__.c.deleted_at.nullable is True


def test_timestamp_columns():
    assert "created_at" in Order.__table__.c
    assert "updated_at" in Order.__table__.c


def test_index_and_check_present():
    index_cols = {tuple(i.columns.keys()) for i in Order.__table__.indexes}
    assert ("total",) in index_cols
    checks = [c for c in Order.__table__.constraints if c.__class__.__name__ == "CheckConstraint"]
    assert checks


def test_meta_table_name_override():
    assert Invoice.__tablename__ == "custom_table"


def test_snake_case_default_without_table_name():
    # Order has no explicit table_name; it should use the snake_case default.
    assert Order.__tablename__ == "order"
