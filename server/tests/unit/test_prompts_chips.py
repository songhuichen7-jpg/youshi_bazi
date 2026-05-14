"""app.prompts.chips — ports prompts.js:929-1006."""
from __future__ import annotations

from tests.unit._chart_fixtures import sample_chart


def test_build_chips_messages_shape():
    from app.prompts.chips import build_messages
    msgs = build_messages(sample_chart(), history=[])
    assert isinstance(msgs, list)
    assert any(m["role"] == "system" for m in msgs)
    system = next(m["content"] for m in msgs if m["role"] == "system")
    assert "刚才回答" in system
    assert "3 个自然追问" in system
    assert '["追问1","追问2","追问3"]' in system


def test_build_chips_messages_uses_latest_dialogue_as_followup_context():
    from app.prompts.chips import build_messages
    msgs = build_messages(sample_chart(), history=[
        {"role": "user", "content": "我的事业接下来怎么走？"},
        {"role": "assistant", "content": "你刚才的重点在流年压力和选择。"},
    ])
    user = msgs[-1]["content"]
    system = msgs[0]["content"]
    assert "【对话记录】" in user
    assert "我的事业接下来怎么走？" in user
    assert "你刚才的重点在流年压力和选择。" in user
    assert "深挖" in system
    assert "落地" in system


def test_parse_chips_json_happy():
    from app.prompts.chips import parse_chips_json
    out = parse_chips_json('["最近事业运如何？", "婚姻缘分时机？", "什么时候发财？"]')
    assert out == ["最近事业运如何？", "婚姻缘分时机？", "什么时候发财？"]


def test_parse_chips_json_malformed_returns_empty():
    from app.prompts.chips import parse_chips_json
    assert parse_chips_json("") == []
    assert parse_chips_json("not json") == []
    assert parse_chips_json("{}") == []


def test_parse_chips_json_wrapped_in_markdown():
    from app.prompts.chips import parse_chips_json
    raw = "```json\n[\"a\",\"b\",\"c\"]\n```"
    out = parse_chips_json(raw)
    assert out == ["a", "b", "c"]


def test_parse_chips_json_caps_followups_at_three():
    from app.prompts.chips import parse_chips_json
    out = parse_chips_json('["a","b","c","d"]')
    assert out == ["a", "b", "c"]
