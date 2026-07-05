"""FastStream integration for alchemiq. Requires the ``[faststream]`` extra."""

from alchemiq.faststream.deps import db_session, repository, unit_of_work
from alchemiq.faststream.lifespan import lifespan
from alchemiq.faststream.publisher import FastStreamPublisher

__all__ = [
    "FastStreamPublisher",
    "lifespan",
    "repository",
    "unit_of_work",
    "db_session",
]
