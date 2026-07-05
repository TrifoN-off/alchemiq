"""Internal ID generators: UUIDv7 and NanoID.

UUIDv7 bit layout (RFC 9562):
  [127:80]  48-bit big-endian millisecond timestamp
  [79:76]   version nibble = 0x7
  [75:64]   12-bit random (rand_a)
  [63:62]   variant = 0b10  (RFC 4122 / RFC 9562)
  [61:0]    62-bit random (rand_b)
"""

from __future__ import annotations

import os
import secrets
import time
import uuid

_LAST_MS: int = 0  # intra-process monotonic guard

_NANOID_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_"


def uuid7() -> uuid.UUID:
    """Return a time-ordered UUIDv7 (RFC 9562).

    Intra-process monotonicity is enforced by bumping the clock forward by 1 ms
    if the current millisecond has not advanced beyond the last generated value.
    """
    global _LAST_MS
    ms = int(time.time() * 1000)
    if ms <= _LAST_MS:
        ms = _LAST_MS + 1
    _LAST_MS = ms

    rand_int = int.from_bytes(os.urandom(10), "big")  # 80 bits

    rand_a = (rand_int >> 62) & 0xFFF  # 12 bits for positions [75:64]
    rand_b = rand_int & 0x3FFFFFFFFFFFFFFF  # 62 bits for positions [61:0]

    value = (ms & 0xFFFFFFFFFFFF) << 80  # 48-bit timestamp in the top bits
    value |= 0x7 << 76  # version nibble
    value |= rand_a << 64  # 12-bit rand_a
    value |= 0b10 << 62  # RFC 4122 variant bits
    value |= rand_b  # 62-bit rand_b

    return uuid.UUID(int=value)


def nanoid(size: int = 21, alphabet: str = _NANOID_ALPHABET) -> str:
    """Return a cryptographically random NanoID string using secrets.choice."""
    return "".join(secrets.choice(alphabet) for _ in range(size))
