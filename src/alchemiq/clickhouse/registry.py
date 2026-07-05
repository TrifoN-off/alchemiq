"""Process-global SQLAlchemy MetaData and mapper registry for ClickHouse models.

Separate from the PostgreSQL registry so CH and PG models never share metadata.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import registry

ch_metadata = MetaData()
"""SQLAlchemy MetaData instance that owns all ClickHouseModel table definitions."""

ch_mapper_registry = registry(metadata=ch_metadata)
"""SQLAlchemy mapper registry for ClickHouseModel subclasses."""
