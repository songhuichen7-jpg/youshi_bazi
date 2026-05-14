"""Slug generation for hepan invites. Same shape as card.slug, prefix 'h_'."""
from __future__ import annotations

import secrets
import string

_ALPHABET = string.ascii_lowercase + string.digits  # 36 chars


def generate_slug() -> str:
    """Return 'h_' + 10 random base-36 chars. ~51 bits entropy."""
    body = "".join(secrets.choice(_ALPHABET) for _ in range(10))
    return f"h_{body}"
