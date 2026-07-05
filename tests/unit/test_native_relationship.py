from __future__ import annotations

import pytest
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alchemiq import Model
from alchemiq._internal.annotations import NATIVE_RELATIONSHIP, _native_spec
from alchemiq.types import PK

pytestmark = pytest.mark.unit


class NRTarget(Model):
    __tablename__ = "native_rel_unit_nr_target"
    id: PK[int]
    name: str


class NRSource(Model):
    __tablename__ = "native_rel_unit_nr_source"
    id: PK[int]
    target_id: Mapped[int] = mapped_column(ForeignKey("native_rel_unit_nr_target.id"))
    target: Mapped[NRTarget] = relationship()  # native escape-hatch (no longer ConfigError)


def test_native_spec_relationship_value() -> None:
    assert _native_spec(Mapped[NRTarget], relationship()) is NATIVE_RELATIONSHIP


def test_native_spec_mapped_model_annotation() -> None:
    from alchemiq.types.base import _MISSING

    assert _native_spec(Mapped[NRTarget], _MISSING) is NATIVE_RELATIONSHIP


def test_native_spec_mapped_list_model() -> None:
    from alchemiq.types.base import _MISSING

    assert _native_spec(Mapped[list[NRTarget]], _MISSING) is NATIVE_RELATIONSHIP


def test_native_spec_mapped_list_scalar_is_column() -> None:
    from alchemiq.types.base import _MISSING

    assert _native_spec(Mapped[list[int]], _MISSING) is list  # ARRAY column, not a relationship


def test_native_spec_mapped_set_model() -> None:
    from alchemiq.types.base import _MISSING

    assert _native_spec(Mapped[set[NRTarget]], _MISSING) is NATIVE_RELATIONSHIP


def test_native_relationship_registered() -> None:
    from alchemiq.model.pipeline import register_native_relationships

    register_native_relationships(NRSource)
    info = NRSource.__alchemiq_relationships__["target"]
    assert info.target is NRTarget
    assert info.direction == "many_to_one"


def test_register_native_relationships_noop_without_registry() -> None:
    # ClickHouse / non-PG models have no __alchemiq_relationships__ - must be a safe no-op.
    from alchemiq.model.pipeline import register_native_relationships

    class _NoRegistry:
        pass

    register_native_relationships(_NoRegistry)  # must not raise


def test_native_column_still_works() -> None:
    # native column path intact: Mapped[dict] = mapped_column(JSONB) is still a native COLUMN
    from sqlalchemy.dialects.postgresql import JSONB

    from alchemiq.types.base import _NativeField

    class NRCol(Model):
        __tablename__ = "native_rel_unit_nr_col"
        id: PK[int]
        payload: Mapped[dict] = mapped_column(JSONB)

    assert isinstance(NRCol.__alchemiq_fields__["payload"], _NativeField)
