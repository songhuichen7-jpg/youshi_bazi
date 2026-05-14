"""prompts/gua: 占卦师 system prompt + classical block.

NOTE: archive/server-mvp/prompts.js:759-803.
"""
from __future__ import annotations

from app.prompts.gua import build_messages


_SAMPLE_GUA = {
    "id": 51, "name": "震", "symbol": "☳☳",
    "upper": "震", "lower": "震",
    "guaci": "震亨。震来虩虩，笑言哑哑。",
    "daxiang": "洊雷，震；君子以恐惧修省。",
    "dongyao": 3,
    "drawn_at": "2026-04-18 14:30:00",
    "source": {"formula": "上卦 (5+4+18)mod8 = 3 离 / 下卦 (27+8)mod8 = 3 离 / 动爻 mod6 = 5"},
}


def test_build_messages_returns_system_and_user():
    msgs = build_messages(question="该不该跳槽", gua=_SAMPLE_GUA, birth_context=None)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1] == {"role": "user", "content": "我的问题：该不该跳槽"}


def test_system_block_includes_format_constraint_and_classical():
    msgs = build_messages(question="?", gua=_SAMPLE_GUA, birth_context=None)
    sys = msgs[0]["content"]
    # Output format constraint
    assert "§卦象" in sys
    assert "§原文" in sys
    assert "§白话" in sys
    assert "§你的问题" in sys
    # Classical anchor block format
    assert "<classical" in sys
    assert "卦辞：" + _SAMPLE_GUA["guaci"] in sys
    assert "大象：" + _SAMPLE_GUA["daxiang"] in sys


def test_birth_context_optional_appended_when_present():
    bc = {"rizhu": "丙", "currentDayun": "戊辰", "currentYear": "丙午"}
    msgs = build_messages(question="?", gua=_SAMPLE_GUA, birth_context=bc)
    sys = msgs[0]["content"]
    assert "【命主背景】" in sys
    assert "丙" in sys and "戊辰" in sys and "丙午" in sys


def test_birth_context_omitted_when_none():
    msgs = build_messages(question="?", gua=_SAMPLE_GUA, birth_context=None)
    assert "【命主背景】" not in msgs[0]["content"]
