"""Unit tests: apply_loaders - error paths + basic options attachment."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from alchemiq import ForeignKey, Model
from alchemiq.exceptions import QueryError
from alchemiq.repository.loading import apply_loaders
from alchemiq.types import PK


class LoArtist(Model):
    __tablename__ = "loading_lo_artist"
    id: PK[int]
    name: str


class LoTrack(Model):
    __tablename__ = "loading_lo_track"
    id: PK[int]
    title: str
    artist: LoArtist = ForeignKey(related_name="tracks")  # type: ignore[assignment]


def test_apply_loaders_adds_options():
    stmt = apply_loaders(select(LoTrack), LoTrack, ("artist",), ())
    assert len(stmt._with_options) == 1  # one loader option attached


def test_unknown_relationship_rejected():
    with pytest.raises(QueryError):
        apply_loaders(select(LoTrack), LoTrack, ("nope",), ())


def test_nested_path_rejected():
    with pytest.raises(QueryError):
        apply_loaders(select(LoTrack), LoTrack, ("artist__name",), ())
