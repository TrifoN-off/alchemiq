import pytest

from alchemiq import Model
from alchemiq.runtime.session import session_scope
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class SessionWidget(Model):
    __tablename__ = "session_widget"
    id: PK[int]
    name: str


async def test_short_session_write_then_read(configured_db):
    async with session_scope(write=True) as s:
        s.add(SessionWidget(id=1, name="alpha"))

    async with session_scope(write=False) as s:
        obj = await s.get(SessionWidget, 1)
        assert obj is not None and obj.name == "alpha"
