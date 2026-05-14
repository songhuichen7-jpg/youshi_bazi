"""Loads card data JSON files into module-level dicts at startup.
Thread-safe via lazy init; idempotent."""
from __future__ import annotations

import json
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "cards"

TYPES: dict = {}
FORMATIONS: dict = {}
SUBTAGS: dict = {}
THRESHOLDS: dict = {}
VERSION: str = ""

_loaded = False


def _read_json(name: str) -> dict:
    return json.loads((_DATA_DIR / name).read_text(encoding="utf-8"))


def load_all() -> None:
    """Idempotent loader. Populate module-level dicts once."""
    global _loaded, VERSION
    if _loaded:
        return
    TYPES.update(_read_json("types.json"))
    FORMATIONS.update(_read_json("formations.json"))
    SUBTAGS.update(_read_json("subtags.json"))
    THRESHOLDS.update(_read_json("state_thresholds.json"))
    VERSION = _read_json("card_version.json")["version"]
    _loaded = True


# Eagerly load at import time so ``from loader import VERSION`` binds the
# real populated string value; load_all() remains idempotent.
load_all()


def illustration_url(filename: str) -> str:
    """Version static card art so browsers let a new visual language arrive."""
    return f"/static/cards/illustrations/{filename}?v={VERSION}"
