"""Migration smoke schema v2: widened title (ALTER -> batch) + new column."""

from __future__ import annotations

from alchemiq import Model
from alchemiq.types import PK, Field, Maybe


class SmigNote(Model):
    __tablename__ = "smig_note"
    id: PK[int]
    title: str = Field(max_length=120)  # type: ignore[assignment]
    body: Maybe[str]
