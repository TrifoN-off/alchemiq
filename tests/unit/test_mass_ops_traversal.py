import pytest

from alchemiq import ForeignKey, Model
from alchemiq.exceptions import QueryError
from alchemiq.query import QuerySet
from alchemiq.types import PK

pytestmark = pytest.mark.unit


class MassFkParent(Model):
    __tablename__ = "mass_fk_parent"
    id: PK[int]
    name: str


class MassFkChild(Model):
    __tablename__ = "mass_fk_child"
    id: PK[int]
    active: bool
    parent: MassFkParent = ForeignKey(related_name="children")  # type: ignore[assignment]


async def test_mass_update_traversal_filter_raises():
    with pytest.raises(QueryError):
        await QuerySet(MassFkChild).filter(parent__name="x").update(active=False)


async def test_mass_delete_traversal_filter_raises():
    with pytest.raises(QueryError):
        await QuerySet(MassFkChild).filter(parent__name="x").delete()
