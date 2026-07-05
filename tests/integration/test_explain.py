from __future__ import annotations

import pytest

from alchemiq import Model, Repository
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class Widget(Model):
    __tablename__ = "explain_widget"
    id: PK[int]
    name: str


async def test_explain_text(configured_db) -> None:
    repo = Repository(Widget)
    await repo.create(id=1, name="a")
    plan = await repo.filter(name="a").explain()
    assert isinstance(plan, str)
    assert "Scan" in plan


async def test_explain_analyze(configured_db) -> None:
    repo = Repository(Widget)
    await repo.create(id=2, name="b")
    plan = await repo.filter(name="b").explain(analyze=True)
    assert isinstance(plan, str)
    assert "Scan" in plan


async def test_explain_json(configured_db) -> None:
    repo = Repository(Widget)
    await repo.create(id=3, name="c")
    plan = await repo.filter(name="c").explain(format="json")
    assert isinstance(plan, list)
    assert "Plan" in plan[0]


async def test_repository_explain_select_all(configured_db) -> None:
    repo = Repository(Widget)
    await repo.create(id=4, name="d")
    plan = await repo.explain()
    assert isinstance(plan, str)
    assert "Scan" in plan
