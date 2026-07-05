import pytest

from alchemiq.signals import (
    clear,
    connect,
    disconnect,
    post_create,
    post_delete,
    pre_update,
)
from alchemiq.signals.registry import dispatch


class Foo:
    pass


@pytest.fixture(autouse=True)
def _clear_signals():
    clear()
    yield
    clear()


async def test_exact_then_global_order():
    calls: list[str] = []

    @post_create(Foo)
    async def exact(instance, **kw):
        calls.append("exact")

    @post_create()
    async def glob(instance, **kw):
        calls.append("global")

    await dispatch("post_create", Foo, Foo())
    assert calls == ["exact", "global"]


async def test_registration_order_preserved():
    calls: list[int] = []

    @post_create(Foo)
    async def first(instance, **kw):
        calls.append(1)

    @post_create(Foo)
    async def second(instance, **kw):
        calls.append(2)

    await dispatch("post_create", Foo, Foo())
    assert calls == [1, 2]


async def test_fail_fast_short_circuits():
    calls: list[int] = []

    @pre_update(Foo)
    async def boom(instance, **kw):
        raise RuntimeError("stop")

    @pre_update(Foo)
    async def never(instance, **kw):
        calls.append(99)

    with pytest.raises(RuntimeError, match="stop"):
        await dispatch("pre_update", Foo, Foo())
    assert calls == []


async def test_event_isolation():
    calls: list[str] = []

    @post_delete(Foo)
    async def on_delete(instance, **kw):
        calls.append("delete")

    await dispatch("post_create", Foo, Foo())
    assert calls == []


async def test_disconnect_and_clear():
    calls: list[str] = []

    async def h(instance, **kw):
        calls.append("h")

    connect(h, sender=Foo, event="post_create")
    disconnect(h, sender=Foo, event="post_create")
    await dispatch("post_create", Foo, Foo())
    assert calls == []
