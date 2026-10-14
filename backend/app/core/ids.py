"""UUIDv7 ids and ISO 8601 UTC timestamps (spec §6.2)."""

from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, datetime


def new_id() -> str:
    """UUIDv7: 48-bit unix-ms timestamp, then random bits (RFC 9562)."""
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ms & (2**48 - 1)) << 80
    value |= 0x7 << 76
    value |= ((rand >> 68) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= rand & (2**62 - 1)
    return str(uuid.UUID(int=value))


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
