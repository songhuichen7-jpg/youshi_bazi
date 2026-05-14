"""Tests for retrieval3.hehua_lookup — 地支合化 deterministic detection.

The motivating case: 1973-09-20 ~10am chart (癸丑 辛酉 己未 己巳).
Previous synthesizer missed the 巳酉丑 三合金局 entirely, leading to
"金 is 喜用" advice that contradicted the very-overpowered food-god.
HehuaRetriever fixes this by *always* scanning earth branches and
emitting a structured EvidenceCard the LLM cannot miss.
"""
from __future__ import annotations

import pytest

from app.retrieval3.hehua_lookup import (
    HEHUA_TYPE_HALF_TRIPLE,
    HEHUA_TYPE_SIX_HE,
    HEHUA_TYPE_TRIPLE_HE,
    HEHUA_TYPE_TRIPLE_HUI,
    HehuaResult,
    detect_hehua,
    hehua_retrieve,
)


def _chart(year: str, month: str, day: str, hour: str) -> dict:
    return {
        "sizhu": {"year": year, "month": month, "day": day, "hour": hour},
    }


# ── 三合（全） ─────────────────────────────────────────────────────────────

def test_si_you_chou_full_metal_combo_veko_case():
    """The motivating real-world chart — 巳酉丑 三合金局, 化神 辛 透干."""
    chart = _chart("癸丑", "辛酉", "己未", "己巳")
    results = detect_hehua(chart)

    triples = [r for r in results if r.type == HEHUA_TYPE_TRIPLE_HE]
    assert len(triples) == 1
    r = triples[0]
    assert sorted(r.branches) == sorted(["巳", "酉", "丑"])
    assert r.element == "金"
    assert r.completeness == 3
    assert r.transparent is True
    assert "辛" in r.transparent_stems
    # 化神金 vs 日主己土 (土生金) → 食伤
    assert r.shishen_family == "食伤"


def test_shen_zi_chen_full_water_combo():
    chart = _chart("壬申", "壬子", "甲辰", "丙寅")
    results = detect_hehua(chart)
    triples = [r for r in results if r.type == HEHUA_TYPE_TRIPLE_HE]
    assert any(
        sorted(r.branches) == sorted(["申", "子", "辰"]) and r.element == "水"
        for r in triples
    )


def test_yin_wu_xu_full_fire_combo():
    chart = _chart("丙寅", "甲午", "乙未", "甲戌")
    results = detect_hehua(chart)
    triples = [r for r in results if r.type == HEHUA_TYPE_TRIPLE_HE]
    assert any(
        sorted(r.branches) == sorted(["寅", "午", "戌"]) and r.element == "火"
        for r in triples
    )


def test_hai_mao_wei_full_wood_combo_transparent_check():
    """化神 木 not透干 (no 甲/乙 in stems) → transparent=False."""
    chart = _chart("丁亥", "癸卯", "戊未", "戊辰")
    results = detect_hehua(chart)
    triples = [r for r in results if r.type == HEHUA_TYPE_TRIPLE_HE]
    assert len(triples) == 1
    r = triples[0]
    assert r.element == "木"
    assert r.transparent is False
    assert r.transparent_stems == ()


# ── 半三合（含中神） ──────────────────────────────────────────────────────

def test_half_triple_metal_si_you():
    """巳酉 (no 丑) → 半三合金."""
    chart = _chart("甲子", "辛酉", "丙寅", "癸巳")
    results = detect_hehua(chart)
    halves = [r for r in results if r.type == HEHUA_TYPE_HALF_TRIPLE]
    assert any(
        set(r.branches) == {"巳", "酉"} and r.element == "金"
        for r in halves
    )


def test_half_triple_metal_you_chou():
    """酉丑 (no 巳) → 半三合金."""
    chart = _chart("乙丑", "辛酉", "丙寅", "戊辰")
    results = detect_hehua(chart)
    halves = [r for r in results if r.type == HEHUA_TYPE_HALF_TRIPLE]
    assert any(
        set(r.branches) == {"酉", "丑"} and r.element == "金"
        for r in halves
    )


def test_half_triple_requires_center_branch():
    """巳丑 without 酉 is NOT a half-triple — the center branch 酉 is
    required (古籍: 半三合必含中神)."""
    chart = _chart("乙丑", "庚辰", "丙寅", "癸巳")  # 巳+丑, no 酉
    results = detect_hehua(chart)
    halves = [r for r in results if r.type == HEHUA_TYPE_HALF_TRIPLE]
    assert not any(
        set(r.branches) == {"巳", "丑"}
        for r in halves
    )


# ── 三会方局 ─────────────────────────────────────────────────────────────

def test_san_hui_eastern_wood():
    chart = _chart("丙寅", "丁卯", "甲辰", "戊申")
    results = detect_hehua(chart)
    huis = [r for r in results if r.type == HEHUA_TYPE_TRIPLE_HUI]
    assert any(
        sorted(r.branches) == sorted(["寅", "卯", "辰"]) and r.element == "木"
        for r in huis
    )


def test_san_hui_western_metal():
    chart = _chart("庚申", "辛酉", "戊戌", "丙寅")
    results = detect_hehua(chart)
    huis = [r for r in results if r.type == HEHUA_TYPE_TRIPLE_HUI]
    assert any(
        sorted(r.branches) == sorted(["申", "酉", "戌"]) and r.element == "金"
        for r in huis
    )


# ── 六合 ──────────────────────────────────────────────────────────────────

def test_liu_he_zi_chou_emitted_but_no_transformation_judgement():
    """六合 子丑 fires, but element=None (古籍分歧, v1 不判化)."""
    chart = _chart("甲子", "丁丑", "戊午", "甲寅")
    results = detect_hehua(chart)
    sixes = [r for r in results if r.type == HEHUA_TYPE_SIX_HE]
    assert any(set(r.branches) == {"子", "丑"} for r in sixes)
    # 六合 v1 不判化神
    zi_chou = next(r for r in sixes if set(r.branches) == {"子", "丑"})
    assert zi_chou.element is None
    assert zi_chou.transparent is False


def test_liu_he_yin_hai():
    chart = _chart("丁亥", "丙寅", "戊午", "甲辰")
    results = detect_hehua(chart)
    sixes = [r for r in results if r.type == HEHUA_TYPE_SIX_HE]
    assert any(set(r.branches) == {"寅", "亥"} for r in sixes)


# ── 空盘 / 无合 ────────────────────────────────────────────────────────────

def test_no_combination_returns_empty():
    """寅 申 卯 戌 — 既无三合也无三会也无六合 (寅申冲, 卯戌六合 ✗ 应触发)."""
    # Build chart with NO recognised combinations
    chart = _chart("甲子", "丙寅", "丁巳", "壬戌")  # 子+寅+巳+戌
    # 寅+巳 半三合? no — 寅午戌 半三合 needs 午 中神
    # 子丑? no 丑
    # 寅亥? no 亥
    # 卯戌? no 卯
    # 巳申? no 申
    # 辰酉? neither
    # So we expect zero hehua results.
    results = detect_hehua(chart)
    assert results == []


def test_missing_paipan_returns_empty():
    assert detect_hehua({}) == []
    assert detect_hehua({"sizhu": {}}) == []


# ── shishen 十神映射 ─────────────────────────────────────────────────────

@pytest.mark.parametrize("day_gan,element,family", [
    ("己", "金", "食伤"),    # 土生金 → 食伤
    ("己", "水", "财"),       # 土克水 → 财
    ("己", "木", "官杀"),     # 木克土 → 官杀
    ("己", "火", "印"),       # 火生土 → 印
    ("己", "土", "比劫"),     # 同我 → 比劫
    ("甲", "水", "印"),       # 水生木 → 印
    ("甲", "金", "官杀"),     # 金克木 → 官杀
])
def test_shishen_family_mapping(day_gan, element, family):
    from app.retrieval3.hehua_lookup import shishen_family
    assert shishen_family(day_gan, element) == family


# ── EvidenceCard 输出（hehua_retrieve） ────────────────────────────────────

@pytest.mark.asyncio
async def test_hehua_retrieve_returns_evidence_cards():
    chart = _chart("癸丑", "辛酉", "己未", "己巳")
    cards = await hehua_retrieve(chart)
    # 巳酉丑全合 (1) + 半三合 巳酉, 酉丑 (2) → 至少1张全合卡
    assert len(cards) >= 1
    full = [c for c in cards if "三合" in c.source and "金局" in c.source]
    assert len(full) == 1
    c = full[0]
    assert c.canonical_key.startswith("hehua::")
    assert c.retriever == "hehua"
    assert c.confidence == 1.0
    assert "巳" in c.text and "酉" in c.text and "丑" in c.text
    assert c.metadata["element"] == "金"
    assert c.metadata["transparent"] is True
    assert c.metadata["shishen_family"] == "食伤"


@pytest.mark.asyncio
async def test_hehua_retrieve_dedup_when_full_includes_half():
    """When 巳酉丑 三合全 fires, the redundant 半三合 卡 should be suppressed
    OR clearly marked subordinate — we choose suppression to keep prompt lean."""
    chart = _chart("癸丑", "辛酉", "己未", "己巳")
    cards = await hehua_retrieve(chart)
    keys = [c.canonical_key for c in cards]
    # Each card should be unique
    assert len(keys) == len(set(keys))
    # No "half" card whose branches are a subset of the full 三合
    full_branches = {"巳", "酉", "丑"}
    for c in cards:
        if c.metadata.get("hehua_type") == HEHUA_TYPE_HALF_TRIPLE:
            half_branches = set(c.metadata["branches"])
            assert not half_branches.issubset(full_branches), (
                f"half-combo {half_branches} should be suppressed when "
                f"full {full_branches} is present"
            )


@pytest.mark.asyncio
async def test_hehua_retrieve_empty_chart():
    assert await hehua_retrieve({}) == []
