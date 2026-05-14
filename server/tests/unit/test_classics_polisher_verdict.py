"""classics_polisher verdict pool — JSON parser + extreme-word filter."""
from __future__ import annotations

import json

from app.services.classics_polisher import (
    _parse_verdict_item,
    _verdict_passes_extreme_check,
)


_RAW_VERDICT = {
    "source": "三命通会·论命格高低",
    "scope": "格局成败",
    "text": "凡正官透干、印星护身者，主清贵之命，宜静守不宜进取。",
}


def test_parse_verdict_happy_path():
    payload = json.dumps({
        "id": "0",
        "quote": "正官透干、印星护身者，主清贵",
        "book": "三命通会",
        "chapter": "论命格高低",
    })
    item = _parse_verdict_item(payload, [_RAW_VERDICT])
    assert item is not None
    assert item["quote"].startswith("正官透干")
    assert item["book"] == "三命通会"


def test_parse_verdict_drops_when_quote_not_in_raw():
    payload = json.dumps({
        "id": "0",
        "quote": "此造大富大贵",  # 不在原文里
        "book": "三命通会", "chapter": "论命",
    })
    assert _parse_verdict_item(payload, [_RAW_VERDICT]) is None


def test_extreme_check_solo_word_rejected():
    assert _verdict_passes_extreme_check("此造主贫") is False
    assert _verdict_passes_extreme_check("克妻克子") is False


def test_extreme_check_with_remedy_accepted():
    assert _verdict_passes_extreme_check("七杀重而身轻，得印化煞则贵") is True
    assert _verdict_passes_extreme_check("贫而能制，亦可成局") is True


def test_extreme_check_no_extreme_word_accepted():
    assert _verdict_passes_extreme_check("正官透干主清贵") is True


def test_parse_verdict_returns_none_on_null_id():
    assert _parse_verdict_item(json.dumps({"id": None}), [_RAW_VERDICT]) is None


def test_extreme_check_does_not_reject_shang_guan_term():
    """伤官 / 伤食 是十神技术词，不是凶词 — extreme filter 不应拒绝。"""
    assert _verdict_passes_extreme_check("伤官配印则贵") is True
    assert _verdict_passes_extreme_check("伤官生财，主富") is True
    assert _verdict_passes_extreme_check("伤食制杀，慷慨多艺") is True


def test_parse_verdict_drops_extreme_quote():
    raw = {
        "source": "X", "scope": "Y",
        "text": "此造主贫夭，无可救药。",
    }
    payload = json.dumps({
        "id": "0", "quote": "此造主贫夭", "book": "X", "chapter": "Y",
    })
    assert _parse_verdict_item(payload, [raw]) is None
