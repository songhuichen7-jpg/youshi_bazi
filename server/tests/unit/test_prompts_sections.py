"""app.prompts.sections — ports prompts.js:276-391."""
from __future__ import annotations

import pytest

from tests.unit._chart_fixtures import sample_chart


def test_build_sections_messages_all_7_sections():
    from app.prompts.sections import build_messages
    for sec in ("career", "personality", "wealth", "relationship",
                "health", "appearance", "special"):
        msgs = build_messages(sample_chart(), retrieved=[], section=sec)
        assert any("role" in m for m in msgs)
        joined = " ".join(m["content"] for m in msgs)
        assert "庚" in joined


def test_build_sections_messages_include_docs_bazi_output_style():
    from app.prompts.sections import build_messages
    msgs = build_messages(sample_chart(), retrieved=[], section="career")
    sys = "\n".join(m["content"] for m in msgs if m["role"] == "system")
    assert "【输出风格预设 — 对齐 docs/bazi-analysis §0】" in sys
    assert "像一个懂命理的朋友在聊天" in sys
    assert "内部 checklist" in sys


def test_parse_sections_text_splits_by_section_marker():
    from app.prompts.sections import parse_sections_text
    raw = "§career\n事业内容\n§wealth\n财富内容\n§relationship\n关系内容\n"
    out = parse_sections_text(raw)
    assert out.get("career", "").strip() == "事业内容"
    assert out.get("wealth", "").strip() == "财富内容"
    assert out.get("relationship", "").strip() == "关系内容"


def test_parse_sections_text_handles_no_marker():
    from app.prompts.sections import parse_sections_text
    out = parse_sections_text("无分节的内容")
    assert isinstance(out, dict)
