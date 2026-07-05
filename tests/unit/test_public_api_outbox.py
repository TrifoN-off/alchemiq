import alchemiq
from alchemiq.model.registry import metadata


def test_publish_exported():
    assert hasattr(alchemiq, "publish")
    assert "publish" in alchemiq.__all__


def test_outboxevent_exported():
    assert hasattr(alchemiq, "OutboxEvent")
    assert "OutboxEvent" in alchemiq.__all__


def test_outbox_table_registered_in_metadata():
    assert "outbox" in metadata.tables
