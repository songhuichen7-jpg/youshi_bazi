"""prompts/router: keyword fallback helpers + LLM router prompt + JSON parser.

NOTE: archive/server-mvp/prompts.js:367-466.
"""
from __future__ import annotations

import pytest

from app.prompts.router import (
    INTENTS,
    KEYWORDS,
    PRIORITY,
    build_messages,
    classify_by_keywords,
    normalize_route_plan,
    parse_router_json,
)


def test_intents_list_complete():
    # NOTE: "media" 是后加的 intent — "用一首歌/电影形容我" 类比喻题
    # 走这个标签，前端把答里的 [[song:...]] / [[movie:...]] / [[flower:...]]
    # token 渲染成媒体卡片。当时 INTENTS 加了 media 但这条测试没改。
    expected = {
        "relationship", "career", "wealth", "timing",
        "personality", "health", "meta", "chitchat", "other",
        "dayun_step", "liunian", "appearance", "special_geju",
        "divination",
        "media",
    }
    assert set(INTENTS) == expected


@pytest.mark.parametrize("text,expected_intent", [
    ("我下周该不该跳槽", "divination"),
    ("今年运气怎么样", "timing"),
    ("接下来两年的关键节点", "timing"),
    ("未来两年我需要注意什么", "timing"),
    ("我和老公感情", "relationship"),
    ("我长得帅吗", "appearance"),
    ("创业能不能成", "divination"),      # "能不能" 命中 divination
    ("飞天禄马是什么", "special_geju"),
    ("七杀是啥意思", "meta"),
    ("我这个人是不是太敏感", "personality"),
    ("最近压力大失眠", "health"),
    ("用一种花形容我这盘", "media"),
    ("我现在像什么花", "media"),
    ("用花来形容我的关系模式", "media"),
    ("我的情绪模式像哪个电影", "media"),
])
def test_classify_by_keywords_priority(text, expected_intent):
    r = classify_by_keywords(text)
    assert r is not None
    assert r["intent"] == expected_intent
    assert r["source"] == "keyword"
    assert r["reason"].startswith("kw:")


def test_media_keyword_route_carries_artifact_decision():
    r = classify_by_keywords("我的情绪模式像哪个电影")
    assert r is not None
    assert r["intent"] == "media"
    assert r["artifact"] == {
        "enabled": True,
        "kind": "movie",
        "reason": "用户明确要求电影类比",
    }


def test_natural_semantic_card_phrasing_routes_to_media_artifacts():
    cases = [
        ("我的性格像哪种花", "flower"),
        ("用一首歌形容我", "song"),
        ("我的情绪模式像哪个电影", "movie"),
    ]

    for text, kind in cases:
        r = classify_by_keywords(text)
        assert r is not None, text
        assert r["intent"] == "media", text
        assert r["artifact"]["enabled"] is True, text
        assert r["artifact"]["kind"] == kind, text


def test_classify_by_keywords_chitchat_only_when_short():
    """chitchat 仅在消息 ≤ 8 字时命中，避免长问题被吞."""
    assert classify_by_keywords("你好") is not None
    assert classify_by_keywords("你好").get("intent") == "chitchat"
    long_msg = "你好我想问问我的事业方向"
    r = classify_by_keywords(long_msg)
    assert r is None or r["intent"] != "chitchat"


def test_media_keywords_require_an_explicit_artifact_kind():
    """防误触发：普通"形容我"应回到性格，不要因为泛词直接出卡片。"""
    r = classify_by_keywords("形容一下我的性格")
    assert r is not None
    assert r["intent"] == "personality"


@pytest.mark.parametrize("text", [
    "最近天气不好会影响我吗",
    "这段关系的味道有点复杂",
    "我今天闻到香水以后有点头晕",
])
def test_weather_scent_casual_mentions_do_not_route_to_media(text):
    """只有明确要求"用天气/气味形容"才走媒体卡，普通闲聊不误触发。"""
    r = classify_by_keywords(text)
    assert r is None or r["intent"] != "media"


@pytest.mark.parametrize("text", [
    "今年桃花运怎么样",
    "为什么我总遇到烂桃花",
    "正缘桃花什么时候来",
])
def test_flower_media_does_not_hijack_relationship_taohua(text):
    """花卡触发保持克制：桃花/桃花运仍是关系问题，不走 flower artifact。"""
    r = classify_by_keywords(text)
    assert r is not None
    assert r["intent"] == "relationship"


def test_classify_by_keywords_no_match_returns_none():
    assert classify_by_keywords("ahsdjkfhakjsdf 无关词") is None


def test_build_messages_includes_recent_history_max_4():
    history = [
        {"role": "user", "content": f"问题{i}"} for i in range(10)
    ]
    msgs = build_messages(history=history, user_message="新问题")
    # 1 system + ≤4 history + 1 user
    assert msgs[0]["role"] == "system"
    assert msgs[-1] == {"role": "user", "content": "新问题"}
    history_msgs = msgs[1:-1]
    assert len(history_msgs) <= 4


def test_router_prompt_requests_artifact_policy():
    msgs = build_messages(history=[], user_message="我的情绪模式像哪个电影")
    sys = msgs[0]["content"]

    assert '"artifact"' in sys
    assert 'enabled' in sys
    assert 'kind' in sys
    assert '像哪个电影/像什么电影/像哪部电影' in sys


def test_parse_router_json_happy():
    raw = '{"intent": "career", "reason": "用户在问跳槽"}'
    r = parse_router_json(raw)
    assert r == {
        "intent": "career",
        "reason": "用户在问跳槽",
        "artifact": {"enabled": False, "kind": None, "reason": ""},
        "secondary_intents": [],
        "needs": {
            "chart": True,
            "classics": True,
            "memory": True,
            "hepan": True,
            "divination": False,
        },
        "retrieval_plan": {"enabled": True, "focus": [], "reason": ""},
        "answer_plan": {
            "format": "core_then_bullets",
            "style": "",
            "should_clarify": False,
        },
    }


def test_parse_router_json_with_artifact_policy():
    raw = (
        '{"intent":"media","reason":"电影类比",'
        '"artifact":{"enabled":true,"kind":"movie","reason":"用户问像哪个电影"}}'
    )
    r = parse_router_json(raw)

    assert r == {
        "intent": "media",
        "reason": "电影类比",
        "artifact": {"enabled": True, "kind": "movie", "reason": "用户问像哪个电影"},
        "secondary_intents": [],
        "needs": {
            "chart": True,
            "classics": False,
            "memory": True,
            "hepan": True,
            "divination": False,
        },
        "retrieval_plan": {"enabled": False, "focus": [], "reason": ""},
        "answer_plan": {
            "format": "core_then_bullets",
            "style": "",
            "should_clarify": False,
        },
    }


def test_parse_router_json_with_turn_plan_for_media_plus_classics():
    raw = """
    {
      "intent": "media",
      "reason": "用户要电影类比，但需要先分析情绪结构",
      "secondary_intents": ["personality", "health"],
      "needs": {
        "chart": true,
        "classics": true,
        "memory": true,
        "hepan": false,
        "divination": false
      },
      "retrieval_plan": {
        "enabled": true,
        "focus": ["性情", "情绪模式", "食伤泄身", "五行刚柔"],
        "reason": "电影类比需要命理依据"
      },
      "artifact": {
        "enabled": true,
        "kind": "movie",
        "reason": "用户明确要求电影"
      },
      "answer_plan": {
        "format": "core_then_bullets",
        "style": "先解释情绪结构，再给电影卡片",
        "should_clarify": false
      }
    }
    """
    r = parse_router_json(raw)

    assert r["intent"] == "media"
    assert r["secondary_intents"] == ["personality", "health"]
    assert r["needs"]["classics"] is True
    assert r["needs"]["hepan"] is False
    assert r["retrieval_plan"] == {
        "enabled": True,
        "focus": ["性情", "情绪模式", "食伤泄身", "五行刚柔"],
        "reason": "电影类比需要命理依据",
    }
    assert r["artifact"]["kind"] == "movie"
    assert r["answer_plan"]["style"] == "先解释情绪结构，再给电影卡片"


def test_parse_router_json_with_codeblock_fence():
    raw = '```json\n{"intent": "wealth", "reason": "财运"}\n```'
    r = parse_router_json(raw)
    assert r["intent"] == "wealth"


def test_normalize_route_plan_rejects_short_answer_for_broad_chart_intents():
    r = normalize_route_plan({
        "intent": "wealth",
        "reason": "财运",
        "answer_plan": {"format": "short_answer"},
    })

    assert r["answer_plan"]["format"] == "core_then_bullets"


def test_parse_router_json_invalid_intent_falls_back_other():
    raw = '{"intent": "nonsense", "reason": "?"}'
    r = parse_router_json(raw)
    assert r["intent"] == "other"


def test_parse_router_json_garbage_falls_back_other():
    assert parse_router_json("总之我觉得是事业问题")["intent"] == "other"
    assert parse_router_json("")["intent"] == "other"
    assert parse_router_json(None)["intent"] == "other"


def test_priority_divination_before_timing():
    """问'今年这事能不能成' — 同时含 timing+divination kw, divination 优先."""
    r = classify_by_keywords("今年这事能不能成")
    assert r is not None
    assert r["intent"] == "divination"


def test_chart_bottom_is_self_structure_not_meta_keyword_fallback():
    r = classify_by_keywords("这盘命的底色是什么")
    assert r is not None
    assert r["intent"] == "personality"
