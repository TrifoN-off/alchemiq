"""OutboxEvent status constants (``pending`` -> ``published`` / ``failed`` -> ``dead``)."""

from __future__ import annotations

PENDING = "pending"
PUBLISHED = "published"
FAILED = "failed"
DEAD = "dead"
