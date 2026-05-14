"""chat_classics_inject._format_segment — pure text composer."""
from __future__ import annotations

from app.services.chat_classics_inject import _format_segment


_PERSONA = {
    "quote": "甲子日元，生于孟春，木当令而不太过。",
    "plain": "木火得位，五行不冲。",
    "book": "滴天髓",
    "chapter": "性情",
    "tier": "case",
    "fit_note": "日干甲、月令寅。",
}
_VERDICT = {
    "quote": "正官透干、印星护身，主清贵",
    "book": "三命通会",
    "chapter": "论命格高低",
}


def test_format_segment_with_both_pieces():
    out = _format_segment(_PERSONA, _VERDICT)
    assert "古书定调" in out
    assert "仅作风格引证，事实仍以前述【结构事实表】为准" in out
    assert "古人画像（滴天髓·性情）：" in out
    assert "甲子日元，生于孟春，木当令而不太过。" in out
    assert "（白话：木火得位，五行不冲。）" in out
    assert "古人定语（三命通会·论命格高低）：正官透干、印星护身，主清贵" in out


def test_format_segment_persona_only():
    out = _format_segment(_PERSONA, None)
    assert "古书定调" in out
    assert "古人画像" in out
    assert "古人定语" not in out  # verdict 缺则那行不出


def test_format_segment_returns_empty_when_persona_missing():
    """没有 persona 就整个段落不发，不要光秃秃发个判语。"""
    assert _format_segment(None, _VERDICT) == ""
    assert _format_segment(None, None) == ""
