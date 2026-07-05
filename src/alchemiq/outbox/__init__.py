"""Transactional outbox - capture, store, and relay domain events."""

from alchemiq.outbox.capture import connect_outbox
from alchemiq.outbox.message import OutboxMessage
from alchemiq.outbox.models import OutboxEvent, is_outbox
from alchemiq.outbox.publisher import Publisher, PublishError, TransientPublishError
from alchemiq.outbox.relay import Relay
from alchemiq.outbox.store import publish

connect_outbox()

__all__ = [
    "OutboxEvent",
    "OutboxMessage",
    "Publisher",
    "PublishError",
    "Relay",
    "TransientPublishError",
    "connect_outbox",
    "is_outbox",
    "publish",
]
