from alchemiq.outbox.capture import _on_create, _on_delete, _on_update, connect_outbox
from alchemiq.signals import clear
from alchemiq.signals.registry import _HANDLERS


def _count(event: str, handler: object) -> int:
    return _HANDLERS.get((event, None), []).count(handler)


def test_connect_outbox_registers_one_global_handler_per_event():
    clear()
    connect_outbox()
    assert _count("post_create", _on_create) == 1
    assert _count("post_update", _on_update) == 1
    assert _count("post_delete", _on_delete) == 1
    clear()


def test_connect_outbox_is_idempotent():
    clear()
    connect_outbox()
    connect_outbox()
    assert _count("post_create", _on_create) == 1
    assert _count("post_update", _on_update) == 1
    assert _count("post_delete", _on_delete) == 1
    clear()


def test_connect_outbox_reregisters_after_clear():
    clear()
    connect_outbox()
    clear()
    connect_outbox()
    assert _count("post_create", _on_create) == 1
    clear()
