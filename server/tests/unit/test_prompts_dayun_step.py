"""app.prompts.dayun_step — ports prompts.js:658-708."""
from __future__ import annotations

import pytest

from tests.unit._chart_fixtures import sample_chart


def test_build_dayun_step_messages_happy():
    from app.prompts.dayun_step import build_messages
    msgs = build_messages(sample_chart(), retrieved=[], step_index=2)
    assert any(m["role"] == "system" for m in msgs)
    joined = " ".join(m["content"] for m in msgs)
    assert "甲申" in joined
    assert "【输出风格预设 — 对齐 docs/bazi-analysis §0】" in joined
    assert "只引用本请求提供的古籍原文锚点" in joined
    assert "直接引用即可" not in joined


def test_build_dayun_step_messages_out_of_range_raises():
    from app.prompts.dayun_step import build_messages
    with pytest.raises((ValueError, IndexError)):
        build_messages(sample_chart(), retrieved=[], step_index=99)
