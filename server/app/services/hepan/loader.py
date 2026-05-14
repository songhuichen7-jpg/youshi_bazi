"""Load hepan/*.json data files into module-level dicts at import time.
Idempotent + thread-safe."""
from __future__ import annotations

import json
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "hepan"

PAIRS: dict = {}        # key = '甲己', value = pair data
DYNAMICS: dict = {}     # full dynamics.json structure
PAIRS_VERSION: str = ""
DYNAMICS_VERSION: str = ""

_loaded = False


def _read_json(name: str) -> dict:
    return json.loads((_DATA_DIR / name).read_text(encoding="utf-8"))


def load_all() -> None:
    """Idempotent loader. Populate module-level dicts once."""
    global _loaded, PAIRS_VERSION, DYNAMICS_VERSION
    if _loaded:
        return
    pairs_data = _read_json("pairs.json")
    dynamics_data = _read_json("dynamics.json")
    PAIRS.update(pairs_data["pairs"])
    PAIRS_VERSION = pairs_data["version"]
    DYNAMICS.update(dynamics_data)
    DYNAMICS_VERSION = dynamics_data["version"]
    _loaded = True


def find_pair(stem_a: str, stem_b: str) -> tuple[dict, bool]:
    """Look up pair data, returning (data, swapped).

    pairs.json keys preserve the spec's authored direction (e.g. '甲己',
    '壬甲'). Many compositions are only listed in one direction; swapped
    is True when the lookup matched (stem_b, stem_a) — callers must then
    swap a_role/b_role consistently.
    """
    if not _loaded:
        load_all()
    direct = PAIRS.get(stem_a + stem_b)
    if direct is not None:
        return direct, False
    swapped = PAIRS.get(stem_b + stem_a)
    if swapped is not None:
        return swapped, True
    raise KeyError(f"no pair data for ({stem_a}, {stem_b})")


# Eagerly load at import time so direct module imports work.
load_all()
