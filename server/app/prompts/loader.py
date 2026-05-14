"""docs/bazi-analysis skill / guide / shards/*.md loaders, lazily cached.

Path resolution:
  - If BAZI_REPO_ROOT env is set, use that.
  - Else walk up from this file until we find a directory containing both
    paipan/ and server/ subdirs (monorepo marker).

NOTE: port of archive/server-mvp/prompts.js:14-34 — boot-time file loading,
but we lazy-load via @lru_cache so tests don't pay the cost and files can
change during dev without restart.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_SKILL_DIR_CANDIDATES = ("bazi-analysis", "skills")


def _repo_root() -> Path:
    env = os.environ.get("BAZI_REPO_ROOT", "").strip()
    if env:
        return Path(env)
    p = Path(__file__).resolve()
    for ancestor in p.parents:
        if (ancestor / "paipan").is_dir() and (ancestor / "server").is_dir():
            return ancestor
    raise RuntimeError("Cannot locate repo root; set BAZI_REPO_ROOT env")


@lru_cache(maxsize=1)
def load_skill() -> str:
    """Read docs/bazi-analysis/SKILL.md; fall back to docs/skills/SKILL.md."""
    return _load_skill_file("SKILL.md")


@lru_cache(maxsize=1)
def load_guide() -> str:
    """Read docs/bazi-analysis/conversation-guide.md; fall back to docs/skills."""
    return _load_skill_file("conversation-guide.md")


def _load_skill_file(filename: str) -> str:
    docs_root = _repo_root() / "docs"
    for dirname in _SKILL_DIR_CANDIDATES:
        p = docs_root / dirname / filename
        try:
            return p.read_text(encoding="utf-8")
        except OSError:
            continue
    return ""


@lru_cache(maxsize=None)
def load_shard(intent: str) -> str:
    """Read shards/<intent>.md; empty string if missing.

    NOTE: prompts.js:27-34 — shards dir holds small topic-specific system-prompt
    fragments. Callers decide which shards to include in their messages.
    """
    p = _repo_root() / "shards" / f"{intent}.md"
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""
