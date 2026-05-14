"""app.prompts.loader: SKILL.md / guide / shards with @lru_cache."""
from __future__ import annotations


def test_repo_root_resolves_from_ancestry():
    from app.prompts.loader import _repo_root
    root = _repo_root()
    assert (root / "paipan").is_dir()
    assert (root / "server").is_dir()


def test_load_skill_returns_content():
    from app.prompts.loader import load_skill
    txt = load_skill()
    assert isinstance(txt, str) and len(txt) > 1000
    assert "bazi" in txt.lower() or "八字" in txt
    assert "behavioral-translation.md" in txt


def test_load_guide_returns_content():
    from app.prompts.loader import load_guide
    txt = load_guide()
    assert isinstance(txt, str) and len(txt) > 100


def test_load_shard_existing():
    from app.prompts.loader import load_shard
    txt = load_shard("core")
    assert isinstance(txt, str) and len(txt) > 0


def test_load_shard_missing_returns_empty():
    from app.prompts.loader import load_shard
    assert load_shard("zzz-nonexistent-intent") == ""


def test_load_skill_lru_cached():
    from app.prompts.loader import load_skill
    load_skill.cache_clear()
    a = load_skill()
    info = load_skill.cache_info()
    assert info.misses == 1
    b = load_skill()
    info2 = load_skill.cache_info()
    assert info2.hits == 1
    assert a is b
