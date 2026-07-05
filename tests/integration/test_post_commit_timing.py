from __future__ import annotations

import pytest

from alchemiq import Model, Repository, UnitOfWork
from alchemiq.runtime.post_commit import enqueue_post_commit
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class PcWidget(Model):
    __tablename__ = "cache_pc_widget"
    id: PK[int]
    name: str


async def test_callback_runs_after_uow_commit(configured_db: None) -> None:
    ran: list[str] = []

    async with UnitOfWork():
        await Repository(PcWidget).create(name="a")
        enqueue_post_commit(_marker(ran, "did-run"))
        assert ran == []  # not yet - still inside the txn
    assert ran == ["did-run"]  # drained after commit


async def test_callback_discarded_on_uow_rollback(configured_db: None) -> None:
    ran: list[str] = []
    with pytest.raises(RuntimeError, match="abort"):
        async with UnitOfWork():
            enqueue_post_commit(_marker(ran, "should-not-run"))
            raise RuntimeError("abort")
    assert ran == []


async def test_callback_runs_after_autocommit_write_scope(configured_db: None) -> None:
    ran: list[str] = []
    from alchemiq.runtime.session import session_scope

    async with session_scope(write=True):
        enqueue_post_commit(_marker(ran, "auto"))
        assert ran == []
    assert ran == ["auto"]


def _marker(target: list[str], value: str):
    async def cb() -> None:
        target.append(value)

    return cb
