from __future__ import annotations

from alchemiq import Model
from alchemiq.types import PK
from alchemiq.types.strings import Password


class KItem(Model):
    __tablename__ = "cache_kitem"
    id: PK[int]
    name: str
    secret: Password
