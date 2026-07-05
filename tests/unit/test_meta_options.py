import dataclasses

import pytest

from alchemiq import Model
from alchemiq.model.meta_options import MetaOptions
from alchemiq.types import PK


class Base(Model):
    __abstract__ = True

    class Meta:
        soft_delete = True


class Doc(Base):
    id: PK[int]

    class Meta:
        timestamps = True


def test_defaults():
    opts = MetaOptions()
    assert opts.soft_delete is False
    assert opts.timestamps is False


def test_meta_attached_and_merged():
    assert Doc.__alchemiq_meta__.soft_delete is True  # inherited from Base
    assert Doc.__alchemiq_meta__.timestamps is True  # own


def test_meta_options_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        MetaOptions().soft_delete = True  # type: ignore[misc]


def test_check_constraint_expression():
    from alchemiq.model.meta_options import Check

    c = Check("x > 0")
    assert c.expression == "x > 0"
    # Check is a frozen dataclass
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.expression = "y > 0"  # type: ignore[misc]


def test_sibling_class_does_not_inherit_soft_delete():
    """A sibling that does NOT inherit the abstract base must not get soft_delete."""
    from alchemiq.model.meta_options import parse_meta

    class Standalone(Model):
        id: PK[int]

        class Meta:
            timestamps = True

    opts = parse_meta(Standalone)
    assert opts.soft_delete is False
    assert opts.timestamps is True
