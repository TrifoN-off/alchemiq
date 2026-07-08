"""Migration smoke schema v1. Subprocess-only: NEVER import from test modules -
v1 and v2 declare the same table name and would collide in one process."""

from __future__ import annotations

from alchemiq import Model
from alchemiq.types import PK, Field


class SmigNote(Model):
    __tablename__ = "smig_note"
    id: PK[int]
    title: str = Field(max_length=50)  # type: ignore[assignment]
