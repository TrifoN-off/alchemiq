"""Integration tests: select_related (joinedload) and prefetch_related (selectinload)."""

from __future__ import annotations

import pytest

from alchemiq import ForeignKey, Model
from alchemiq.query import QuerySet
from alchemiq.runtime.session import session_scope
from alchemiq.types import PK

pytestmark = pytest.mark.integration


class PrefetchArtist(Model):
    __tablename__ = "prefetch_artist"
    id: PK[int]
    name: str


class PrefetchTrack(Model):
    __tablename__ = "prefetch_track"
    id: PK[int]
    title: str
    artist: PrefetchArtist = ForeignKey(related_name="tracks")  # type: ignore[assignment]


async def _seed() -> None:
    async with session_scope(write=True) as s:
        s.add(PrefetchArtist(id=1, name="Bowie"))
        await s.flush()
        s.add_all(
            [
                PrefetchTrack(id=1, title="Heroes", artist_id=1),
                PrefetchTrack(id=2, title="Ashes", artist_id=1),
            ]
        )


async def test_select_related_loads_forward(configured_db):
    await _seed()
    track = await QuerySet(PrefetchTrack).select_related("artist").filter(id=1).first()
    assert track is not None
    assert track.artist.name == "Bowie"  # no RelationNotLoaded


async def test_prefetch_related_loads_collection(configured_db):
    await _seed()
    artist = await QuerySet(PrefetchArtist).prefetch_related("tracks").filter(id=1).first()
    assert artist is not None
    assert {t.title for t in artist.tracks} == {"Heroes", "Ashes"}
