"""End-to-end: hehua EvidenceCard → v1_hit dict → build_classical_anchor.

Verifies that the hehua family's structural facts (合化类型, 化神, 透干 stems,
十神 family) survive the dict-collapse path and reach the LLM system prompt
in a form the shards/core.md power-arena rule can consume.
"""
from __future__ import annotations

import pytest

from app.prompts.anchor import build_classical_anchor
from app.retrieval3.hehua_lookup import hehua_retrieve


def _chart(year, month, day, hour):
    return {"sizhu": {"year": year, "month": month, "day": day, "hour": hour}}


@pytest.mark.asyncio
async def test_veko_case_hehua_card_renders_into_anchor():
    """The 1973 case — 巳酉丑 三合金 must appear in the anchor block with
    the 化神 information the LLM needs to avoid the "金 is 喜用" bug."""
    chart = _chart("癸丑", "辛酉", "己未", "己巳")
    cards = await hehua_retrieve(chart)
    hits = [c.to_v1_hit() for c in cards]
    block = build_classical_anchor(hits, terse=False)

    # The structural label must appear so shards/core.md's hehua rule fires.
    assert "支持:地支合化(结构性)" in block

    # The card text must carry the key structural facts.
    assert "巳酉丑" in block
    assert "三合金局" in block
    assert "化神透干" in block and "辛" in block
    # 十神家族 — without this the LLM cannot judge over-strength.
    assert "食伤" in block


@pytest.mark.asyncio
async def test_no_hehua_no_anchor_contamination():
    """Charts without any 合化 patterns should not emit a hehua card,
    and the anchor block (if other retrievers had hits) must not mention
    地支合化 spuriously."""
    chart = _chart("甲子", "丙寅", "丁巳", "壬戌")
    cards = await hehua_retrieve(chart)
    assert cards == []
    # If we render an empty list, nothing is produced.
    assert build_classical_anchor([], terse=False) == ""


@pytest.mark.asyncio
async def test_anchor_marks_first_hit_as_primary():
    """The ★ 首选锚点 label is given to the first hit. We don't reorder
    hehua to the top in v1 — but when the LLM sees the structural label
    in the support field, it should weight it appropriately regardless of
    position. This test just confirms the rendering contract is intact."""
    chart = _chart("癸丑", "辛酉", "己未", "己巳")
    cards = await hehua_retrieve(chart)
    hits = [c.to_v1_hit() for c in cards]
    block = build_classical_anchor(hits, terse=False)
    # First hit gets the star marker — even though hehua is alone here.
    assert "★ 首选锚点" in block
