"""Load the canonical evidence index built by scripts/eval/build_canonical_index.py.

Cached singletons: each retriever calls into here at module init.

Re-running build_canonical_index requires restarting the process to pick up
new data — this is fine for retrieval3 since the index changes only when
the corpus changes (rebuild_canonical_index is part of the corpus build).
"""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# Default lives at server/var/eval/canonical_index.json.
# Set CANONICAL_INDEX_PATH env to override (tests, alt corpus).
_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "var" / "eval" / "canonical_index.json"


def _path() -> Path:
    env = os.environ.get("CANONICAL_INDEX_PATH")
    return Path(env) if env else _DEFAULT_PATH


@lru_cache(maxsize=1)
def _data() -> dict:
    p = _path()
    if not p.exists():
        logger.warning(
            "canonical_index.json not found at %s — retrieval3 will return [] "
            "until you run scripts.eval.build_canonical_index", p,
        )
        return {"qtbj_sections": [], "smth_entries": [], "stats": {}}
    return json.loads(p.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def qtbj_index() -> dict[tuple[str, str], dict]:
    """Lookup table keyed by (day_gan, month_zhi) → canonical section dict."""
    out: dict[tuple[str, str], dict] = {}
    for s in _data().get("qtbj_sections", []):
        out[(s["day_gan"], s["month_zhi"])] = s
    logger.info("retrieval3 qtbj_index: %d entries", len(out))
    return out


@lru_cache(maxsize=1)
def smth_index() -> dict[tuple[str, str], dict]:
    """Lookup table keyed by (day_pillar, hour_pillar) → canonical entry dict."""
    out: dict[tuple[str, str], dict] = {}
    for e in _data().get("smth_entries", []):
        out[(e["day_pillar"], e["hour_pillar"])] = e
    logger.info("retrieval3 smth_index: %d entries", len(out))
    return out


@lru_cache(maxsize=1)
def shensha_entries() -> list[dict]:
    return list(_data().get("shensha_entries", []))


@lru_cache(maxsize=1)
def geju_entries() -> list[dict]:
    return list(_data().get("geju_entries", []))


@lru_cache(maxsize=1)
def liuqin_entries() -> list[dict]:
    return list(_data().get("liuqin_entries", []))


@lru_cache(maxsize=1)
def appearance_entries() -> list[dict]:
    return list(_data().get("appearance_entries", []))


@lru_cache(maxsize=1)
def appearance_index() -> dict[tuple[str, str], dict]:
    """(kind, axis_char) → entry. kind ∈ {gan, zhi, general}."""
    out: dict[tuple[str, str], dict] = {}
    for e in _data().get("appearance_entries", []):
        out[(e["kind"], e["aspect"])] = e
    return out


@lru_cache(maxsize=1)
def concept_entries() -> list[dict]:
    return list(_data().get("concept_entries", []))


@lru_cache(maxsize=1)
def theory_entries() -> list[dict]:
    return list(_data().get("theory_entries", []))


def reset_cache() -> None:
    """Tests / index rebuild trigger this."""
    _data.cache_clear()
    qtbj_index.cache_clear()
    smth_index.cache_clear()
    shensha_entries.cache_clear()
    geju_entries.cache_clear()
    liuqin_entries.cache_clear()
    appearance_entries.cache_clear()
    appearance_index.cache_clear()
    concept_entries.cache_clear()
    theory_entries.cache_clear()
