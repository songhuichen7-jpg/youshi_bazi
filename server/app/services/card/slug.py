"""Slug generation and deterministic birth hashing."""
from __future__ import annotations

import hashlib
import secrets
import string

_ALPHABET = string.ascii_lowercase + string.digits  # 36 chars


def generate_slug() -> str:
    """Return 'c_' + 10 random base-36 chars. ~51 bits entropy."""
    body = "".join(secrets.choice(_ALPHABET) for _ in range(10))
    return f"c_{body}"


def birth_hash(year: int, month: int, day: int, hour: int, minute: int) -> str:
    """SHA256 of canonical birth string. Used to dedupe shares."""
    canonical = f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
