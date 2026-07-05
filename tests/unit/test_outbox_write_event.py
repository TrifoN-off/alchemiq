from typing import Any

from alchemiq.outbox.store import _write_event
from alchemiq.types import Nothing, Some


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)


def test_minimal_event_has_topic_payload_and_nothing_optionals():
    s = _FakeSession()
    _write_event(s, topic="t.created", payload={"a": 1})
    (ev,) = s.added
    assert ev.topic == "t.created"
    assert ev.payload == {"a": 1}
    assert ev.aggregate_type is Nothing
    assert ev.aggregate_id is Nothing
    assert ev.event_type is Nothing
    assert ev.headers is Nothing


def test_provided_optionals_are_wrapped_in_some():
    s = _FakeSession()
    _write_event(
        s,
        topic="orders.created",
        payload={},
        aggregate_type="orders",
        aggregate_id="42",
        event_type="created",
        headers={"k": "v"},
    )
    (ev,) = s.added
    assert ev.aggregate_type == Some("orders")
    assert ev.aggregate_id == Some("42")
    assert ev.event_type == Some("created")
    assert ev.headers == Some({"k": "v"})
