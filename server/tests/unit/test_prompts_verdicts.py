"""app.prompts.verdicts.build_messages — ports prompts.js:815-883."""
from __future__ import annotations

from tests.unit._chart_fixtures import sample_chart


def test_build_verdicts_messages_shape():
    from app.prompts.verdicts import build_messages
    msgs = build_messages(sample_chart(), retrieved=[])
    assert isinstance(msgs, list)
    assert all("role" in m and "content" in m for m in msgs)
    roles = [m["role"] for m in msgs]
    assert "system" in roles and "user" in roles


def test_build_verdicts_messages_system_includes_chart():
    from app.prompts.verdicts import build_messages
    msgs = build_messages(sample_chart(), retrieved=[])
    sys = "\n".join(m["content"] for m in msgs if m["role"] == "system")
    assert "庚午" in sys
    assert "运行时约束" in sys


def test_build_verdicts_messages_user_prompt_fixed():
    from app.prompts.verdicts import build_messages
    msgs = build_messages(sample_chart(), retrieved=[])
    user = [m for m in msgs if m["role"] == "user"][0]["content"]
    assert "判词" in user or "不要前言" in user


def test_build_verdicts_messages_with_retrieval():
    from app.prompts.verdicts import build_messages
    retrieved = [{"source": "滴天髓", "scope": "full", "chars": 200,
                  "text": "庚金带杀，刚健为最"}]
    msgs = build_messages(sample_chart(), retrieved=retrieved)
    sys = "\n".join(m["content"] for m in msgs if m["role"] == "system")
    assert "滴天髓" in sys or "庚金带杀" in sys


def test_build_verdicts_messages_aligns_docs_bazi_style_and_quote_policy():
    from app.prompts.verdicts import build_messages
    msgs = build_messages(sample_chart(), retrieved=[])
    sys = "\n".join(m["content"] for m in msgs if m["role"] == "system")
    assert "【输出风格预设 — 对齐 docs/bazi-analysis §0】" in sys
    assert "只引用本请求提供的古籍原文锚点" in sys
    assert "可自由引用" not in sys
    assert "直接引用原文即可" not in sys
