"""classics_polisher.polish_classics_for_chart orchestration test.

LLM call is patched so the test focuses on parallel orchestration + result
shape without making real API calls.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services import classics_polisher


_CHART = {
    "PAIPAN": {
        "rizhu": "甲子",
        "sizhu": {"year": "丙申", "month": "丙寅", "day": "甲子", "hour": "甲戌"},
        "dayStrength": "身强",
        "geJu": {"mainCandidate": {"shishen": "建禄"}},
    }
}

_PERSONA_HIT = {
    "source": "滴天髓·性情",
    "scope": "六亲论·性情",
    "text": "甲子日元，生于孟春，木当令而不太过……为人不苟，无骄谄刻薄之行，有廉恭仁厚之风。",
}
_VERDICT_HIT = {
    "source": "三命通会·论命格高低",
    "scope": "格局成败",
    "text": "凡正官透干、印星护身者，主清贵之命，宜静守不宜进取。",
}


@pytest.mark.asyncio
async def test_polish_runs_both_pools_in_parallel():
    persona_response = (
        json.dumps({
            "id": "0",
            "quote": "甲子日元，生于孟春，木当令而不太过。",
            "plain": "木火得位，五行不冲。",
            "fit_note": "日干甲、月令寅、建禄当令。",
            "tier": "case", "book": "滴天髓", "chapter": "性情",
        }),
        "fast-model",
    )
    verdict_response = (
        json.dumps({
            "id": "0", "quote": "正官透干、印星护身者，主清贵",
            "book": "三命通会", "chapter": "论命格高低",
        }),
        "fast-model",
    )
    chat_mock = AsyncMock(side_effect=[persona_response, verdict_response])
    with patch.object(classics_polisher, "chat_once_with_fallback", chat_mock):
        result = await classics_polisher.polish_classics_for_chart(
            _CHART, [_PERSONA_HIT], [_VERDICT_HIT],
        )
    assert result["persona"] is not None
    assert result["persona"]["tier"] == "case"
    assert result["verdict"] is not None
    assert "正官透干" in result["verdict"]["quote"]


@pytest.mark.asyncio
async def test_polish_handles_empty_pools():
    result = await classics_polisher.polish_classics_for_chart(_CHART, [], [])
    assert result == {"persona": None, "verdict": None}


@pytest.mark.asyncio
async def test_polish_drops_persona_no_match_hits_before_llm():
    """完全无关的命例 (e.g. 丙日盘) — pre-filter 应把它扔掉，不进 LLM。"""
    bad_hit = dict(_PERSONA_HIT, text="丙午日元，生于仲夏，火炎土燥……")
    chat_mock = AsyncMock(return_value=(json.dumps({"id": None}), "fast-model"))
    with patch.object(classics_polisher, "chat_once_with_fallback", chat_mock):
        result = await classics_polisher.polish_classics_for_chart(
            _CHART, [bad_hit], [],
        )
    # 全部 hits 被过滤掉，根本没调 LLM
    assert chat_mock.call_count == 0
    assert result["persona"] is None
