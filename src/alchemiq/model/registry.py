"""Shared SQLAlchemy ``MetaData`` and ``registry`` singletons for all mapped models."""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import registry

metadata = MetaData()
mapper_registry = registry(metadata=metadata)
