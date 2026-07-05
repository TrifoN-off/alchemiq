from dataclasses import FrozenInstanceError

import pytest

from alchemiq.outbox.message import OutboxMessage, to_message
from alchemiq.outbox.models import OutboxEvent


def test_to_message_unwraps_present_maybe_columns():
    row = OutboxEvent(
        id=1,
        topic="orders.created",
        payload={"x": 1},
        aggregate_type="orders",
        aggregate_id="42",
        event_type="created",
        headers={"trace": "abc"},
    )
    msg = to_message(row)
    assert msg == OutboxMessage(
        id=1,
        topic="orders.created",
        payload={"x": 1},
        headers={"trace": "abc"},
        aggregate_type="orders",
        aggregate_id="42",
        event_type="created",
    )


def test_to_message_maps_unpassed_columns_to_none():
    # Optional columns never passed to the constructor stay raw None (un-instrumented),
    # never routed through the set-listener - _unwrap passes them through unchanged.
    row = OutboxEvent(id=2, topic="manual.event", payload={})
    msg = to_message(row)
    assert msg.headers is None
    assert msg.aggregate_type is None
    assert msg.aggregate_id is None
    assert msg.event_type is None


def test_to_message_maps_explicit_none_to_none():
    # Passing explicit None routes columns through MaybeField.validate -> Nothing,
    # which _unwrap resolves to None (the real DB-loaded-null branch).
    row = OutboxEvent(
        id=3,
        topic="t",
        payload={},
        headers=None,
        aggregate_type=None,
        aggregate_id=None,
        event_type=None,
    )
    msg = to_message(row)
    assert msg.headers is None
    assert msg.aggregate_type is None
    assert msg.aggregate_id is None
    assert msg.event_type is None


def test_outbox_message_is_frozen():
    msg = OutboxMessage(
        id=1,
        topic="t",
        payload={},
        headers=None,
        aggregate_type=None,
        aggregate_id=None,
        event_type=None,
    )
    with pytest.raises(FrozenInstanceError):
        msg.id = 2  # type: ignore[misc]
