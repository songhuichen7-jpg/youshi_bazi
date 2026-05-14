"""prompts/expert: chart slice + INTENT_GUIDE + build_messages.

NOTE: deviation from archive/server-mvp/prompts.js:472-562 — pick_chart_slice
operates on the FLAT chart.paipan shape used by the Python paipan engine,
not the JS UI-shape. FORCE/GUARDS filtering is dropped (data not in shape).
"""
from __future__ import annotations

import pytest

from app.prompts.expert import (
    FALLBACK_STYLE,
    INTENT_GUIDE,
    build_messages,
    pick_chart_slice,
)


# Flat shape — matches the engine output stored in chart.paipan.
_SAMPLE_PAIPAN = {
    "sizhu": {"year": "甲子", "month": "乙丑", "day": "丙寅", "hour": "丁卯"},
    "shishen": {"year": "正印", "month": "比肩", "day": "", "hour": "正印"},
    "cangGan": {"year": [], "month": [], "day": [], "hour": []},
    "naYin": {"year": "海中金", "month": "海中金", "day": "炉中火", "hour": "炉中火"},
    "rizhu": "丙",
    "todayYmd": "2026-04-18",
    "todayYearGz": "丙午",
    "todayMonthGz": "壬辰",
    "dayun": {
        "list": [
            {"ganZhi": "丙寅", "shiShen": "比肩", "startAge": 5,  "startYear": 1995, "endYear": 2004},
            {"ganZhi": "丁卯", "shiShen": "劫财", "startAge": 15, "startYear": 2005, "endYear": 2014},
            {"ganZhi": "戊辰", "shiShen": "食神", "startAge": 25, "startYear": 2015, "endYear": 2024},
            {"ganZhi": "己巳", "shiShen": "伤官", "startAge": 35, "startYear": 2025, "endYear": 2034},
            {"ganZhi": "庚午", "shiShen": "偏财", "startAge": 45, "startYear": 2035, "endYear": 2044},
        ],
    },
}


def test_intent_guide_covers_all_chat_intents():
    expected = {
        "relationship", "career", "wealth", "timing", "personality",
        "health", "meta", "chitchat", "other", "appearance", "special_geju",
        "liunian", "dayun_step",
    }
    assert expected.issubset(set(INTENT_GUIDE.keys()))


def test_pick_chart_slice_chitchat_returns_none():
    assert pick_chart_slice(_SAMPLE_PAIPAN, "chitchat") is None


def test_pick_chart_slice_other_returns_input_unchanged():
    """Non-timing, non-chitchat intents pass through (no FORCE/GUARDS to filter)."""
    s = pick_chart_slice(_SAMPLE_PAIPAN, "other")
    assert s is _SAMPLE_PAIPAN
    s2 = pick_chart_slice(_SAMPLE_PAIPAN, "career")
    assert s2 is _SAMPLE_PAIPAN
    s3 = pick_chart_slice(_SAMPLE_PAIPAN, "relationship")
    assert s3 is _SAMPLE_PAIPAN


def test_pick_chart_slice_timing_windows_dayun_around_current():
    """today=2026 lives in idx=3 (己巳). Window = dayun[max(0,2):6] = dayun[2:6]."""
    s = pick_chart_slice(_SAMPLE_PAIPAN, "timing")
    assert s is not _SAMPLE_PAIPAN  # new dict
    windowed = s["dayun"]["list"]
    gzs = [d["ganZhi"] for d in windowed]
    assert "己巳" in gzs
    assert len(windowed) <= 4
    # The original is not mutated
    assert len(_SAMPLE_PAIPAN["dayun"]["list"]) == 5


def test_pick_chart_slice_timing_with_no_match_falls_back_to_first_three():
    """If no dayun contains today's year, take the first 3 steps."""
    p = {**_SAMPLE_PAIPAN, "todayYmd": "1900-01-01"}
    s = pick_chart_slice(p, "timing")
    windowed = s["dayun"]["list"]
    # First 3 from sample
    assert [d["ganZhi"] for d in windowed] == ["丙寅", "丁卯", "戊辰"]


def test_pick_chart_slice_returns_none_on_empty_paipan():
    assert pick_chart_slice({}, "career") is None
    assert pick_chart_slice(None, "career") is None


def test_build_messages_includes_chart_context_for_non_chitchat():
    """Critical: chart-context block must reach the LLM for normal intents."""
    msgs = build_messages(
        paipan=_SAMPLE_PAIPAN, history=[],
        user_message="今年我适合换工作吗",
        intent="career", retrieved=[],
    )
    sys = msgs[0]["content"]
    # compact_chart_context emits "【命盘上下文】" — must be present
    assert "【命盘上下文】" in sys
    # And key chart fields make it through
    assert "丙" in sys           # rizhu
    assert "甲子" in sys         # year sizhu


def test_build_messages_prepends_time_anchor_to_user_message():
    history = [{"role": "user", "content": "之前问题"}, {"role": "assistant", "content": "之前回答"}]
    msgs = build_messages(
        paipan=_SAMPLE_PAIPAN, history=history,
        user_message="今年我适合换工作吗",
        intent="career", retrieved=[],
    )
    last = msgs[-1]
    assert last["role"] == "user"
    assert "【当前时间锚】" in last["content"]
    assert "今年我适合换工作吗" in last["content"]


def test_build_messages_uses_prebudgeted_history_without_local_eight_message_cutoff():
    history = [{"role": "user", "content": f"q{i}"} for i in range(20)]
    msgs = build_messages(
        paipan=_SAMPLE_PAIPAN, history=history,
        user_message="新", intent="other", retrieved=[],
    )
    assert len(msgs) == 22  # 1 system + 20 prebudgeted history + 1 user
    assert [m["content"] for m in msgs[1:21]] == [f"q{i}" for i in range(20)]


def test_build_messages_includes_client_page_context_for_references():
    msgs = build_messages(
        paipan=_SAMPLE_PAIPAN,
        history=[],
        user_message="上面第一条是什么意思",
        intent="career",
        retrieved=[],
        client_context={
            "view": "chart",
            "context_label": "戊午大运",
            "classics": [
                {
                    "source": "穷通宝鉴",
                    "scope": "论甲木 · 三秋甲木",
                    "quote": "七月甲木，丁火为尊，庚金次之。",
                    "plain": "七月甲木先看丁火，再看庚金。",
                    "match": "本盘甲木生申月，庚透而丁藏。",
                }
            ],
        },
    )
    sys = msgs[0]["content"]
    assert "【当前界面上下文】" in sys
    assert "当前焦点：戊午大运" in sys
    assert "穷通宝鉴 · 论甲木 · 三秋甲木" in sys
    assert "七月甲木，丁火为尊，庚金次之。" in sys
    assert "本盘甲木生申月，庚透而丁藏。" in sys


def test_build_messages_includes_kline_liunian_focus():
    """K 线点流年 → client_context.kline 进系统提示，而**不**进 user message。"""
    msgs = build_messages(
        paipan=_SAMPLE_PAIPAN,
        history=[],
        user_message="2026 这年我该重点抓什么",
        intent="liunian",
        retrieved=[],
        client_context={
            "view": "timing",
            "kline": {
                "scope": "liunian",
                "label": "2026 丙午（当前流年）",
                "phase": "当前",
                "year": 2026,
                "gz": "丙午",
                "year_shishen": "正官/正印",
                "dayun_gz": "乙卯",
                "dayun_shishen": "偏印/偏印",
                "gan_wuxing": "丙火",
                "zhi_wuxing": "午火",
                "day_pillar": "丁酉",
                "yongshen": "甲木",
                "relations": "大运乙卯与流年丙午对冲；午未六合化土",
                "shensha": "桃花",
                "band": "平",
                "score": -0.41,
                "volatility": "中",
            },
        },
    )
    sys = msgs[0]["content"]
    user = msgs[-1]["content"]
    # 系统提示里能拿到结构化字段
    assert "【K 线焦点：流年】" in sys
    assert "2026 丙午" in sys
    assert "正官/正印" in sys
    assert "桃花" in sys
    assert "对冲" in sys
    assert "能量评级：平" in sys
    # 用户消息保持干净 — 不含 K 线结构化字段，K 线信息只走系统提示
    assert "上下文：" not in user
    assert "能量评级" not in user
    assert "桃花" not in user
    assert "2026 这年我该重点抓什么" in user


def test_build_messages_includes_kline_dayun_focus():
    msgs = build_messages(
        paipan=_SAMPLE_PAIPAN, history=[],
        user_message="这一运的主线是什么",
        intent="dayun", retrieved=[],
        client_context={
            "view": "timing",
            "kline": {
                "scope": "dayun",
                "label": "乙卯 大运（2017–2026 · 当前）",
                "phase": "当前",
                "gz": "乙卯",
                "shishen": "偏印/偏印",
                "start_year": 2017,
                "end_year": 2026,
                "age_start": 28,
                "day_pillar": "丁酉",
                "yongshen": "甲木",
                "band": "顺",
                "score": 0.62,
                "range": 1.4,
                "shensha": "桃花、华盖",
            },
        },
    )
    sys = msgs[0]["content"]
    assert "【K 线焦点：大运】" in sys
    assert "乙卯" in sys
    assert "2017–2026" in sys
    assert "能量评级：顺" in sys
    assert "桃花" in sys


def test_build_messages_includes_chart_force_analysis():
    """前端 buildChartForceSummary 算好的命局结构分析应进系统提示, 让 LLM
    跟 K 线读同一份地基, 不必每次现场重推。"""
    msgs = build_messages(
        paipan=_SAMPLE_PAIPAN,
        history=[],
        user_message="这盘整体怎样",
        intent="personality",
        retrieved=[],
        client_context={
            "view": "chart",
            "chart_force": (
                "身强弱: 身弱\n格局: 七杀格\n用神: 丁火 (调候)\n"
                "力量场:\n  重 (透+根) 七杀\n  弱 比肩\n"
                "关键判断:\n  · 杀无制 — 七杀重而印 / 食伤皆无, 整盘'凶根'"
            ),
        },
    )
    sys = msgs[0]["content"]
    assert "【命局定盘" in sys
    assert "身强弱: 身弱" in sys
    assert "七杀格" in sys
    assert "杀无制" in sys
    # 注脚也得在 — 让 LLM 把这块当"已知前提", 并优先引用古籍
    assert "直接采信" in sys
    assert "至少引用一处" in sys
    # 不该有"前端确定性"等 leak (前端泄漏关键短语 — 但允许 媒体卡 markup 里
    # 解释"前端会渲染"这种, 那是讲渲染机制不是分析来源)
    assert "前端确定性" not in sys
    assert "前端给的" not in sys
    assert "分析模块" not in sys


def test_build_messages_includes_long_term_conversation_memory():
    msgs = build_messages(
        paipan=_SAMPLE_PAIPAN,
        history=[],
        user_message="继续讲刚才那个判断",
        intent="career",
        retrieved=[],
        memory_summary="用户之前重点关心七杀格、丁火用神、癸水阻丁，以及古籍旁证是否贴盘。",
    )
    sys = msgs[0]["content"]
    assert "【长期对话记忆】" in sys
    assert "七杀格" in sys
    assert "癸水阻丁" in sys


def test_build_messages_chitchat_skips_chart_context():
    msgs = build_messages(
        paipan=_SAMPLE_PAIPAN, history=[],
        user_message="你好", intent="chitchat", retrieved=[],
    )
    sys = msgs[0]["content"]
    # chitchat → pick_chart_slice returns None → no chart block
    assert "【命盘上下文】" not in sys


def test_build_messages_artifact_rules_gate_flower_card():
    msgs = build_messages(
        paipan=_SAMPLE_PAIPAN,
        history=[],
        user_message="今年桃花运怎么样",
        intent="other",
        retrieved=[],
    )
    sys = msgs[0]["content"]

    assert "花 → [[flower:花名|一句短说明]]" in sys
    assert "桃花运/烂桃花不是花卡请求" in sys


def test_build_messages_artifact_rules_limit_cards_to_explicit_media_requests():
    msgs = build_messages(
        paipan=_SAMPLE_PAIPAN,
        history=[],
        user_message="这盘命的底色是什么",
        intent="other",
        retrieved=[],
    )
    sys = msgs[0]["content"]

    assert "只有用户明确要求用歌曲/电影/花来形容、推荐或更换时，才输出对应卡片标记" in sys
    assert "普通命理回答里只是顺手拿作品打比方时，不要输出 [[song:" in sys
    assert "用户问底色、核心矛盾、擅长什么、事业/感情/流年时，不要主动塞作品卡" in sys
    assert "像哪个电影/像什么电影/像哪部电影" in sys


def test_build_messages_route_plan_can_enable_movie_card():
    msgs = build_messages(
        paipan=_SAMPLE_PAIPAN,
        history=[],
        user_message="我的情绪模式像哪个电影",
        intent="media",
        retrieved=[],
        route_plan={
            "intent": "media",
            "artifact": {
                "enabled": True,
                "kind": "movie",
                "reason": "用户明确要求电影类比",
            },
        },
    )
    sys = msgs[0]["content"]

    assert "【本轮路由决策】" in sys
    assert "卡片：启用 movie" in sys
    assert "必须输出 1 个 [[movie:" in sys


def test_build_messages_route_plan_can_disable_cards():
    msgs = build_messages(
        paipan=_SAMPLE_PAIPAN,
        history=[],
        user_message="这盘命的底色是什么",
        intent="other",
        retrieved=[],
        route_plan={
            "intent": "other",
            "artifact": {
                "enabled": False,
                "kind": None,
                "reason": "普通命理分析",
            },
        },
    )
    sys = msgs[0]["content"]

    assert "卡片：不启用" in sys
    assert "即使顺手提到电影/歌/书，也只用纯文本《作品名》" in sys


def test_build_messages_response_structure_discourages_wall_text():
    msgs = build_messages(
        paipan=_SAMPLE_PAIPAN,
        history=[],
        user_message="我天生擅长什么",
        intent="personality",
        retrieved=[],
    )
    sys = msgs[0]["content"]

    assert "超过 400 字的回答先给一句核心判断" in sys
    assert "再用 2-5 个分点" in sys
    assert "每个分点只讲一个核心意思" in sys
    assert "不要连续写成长墙段落" in sys


def test_build_messages_blocks_bare_internal_chart_ref_ids():
    msgs = build_messages(
        paipan=_SAMPLE_PAIPAN,
        history=[],
        user_message="接下来两年的关键节点",
        intent="timing",
        retrieved=[],
    )
    sys = msgs[0]["content"]

    assert "不要输出裸内部引用" in sys
    assert "liunian.2026|丙午" in sys
    assert "dayun.1|戊午运" in sys
    assert "如果拿不准标记格式，就直接写丙午、戊午运" in sys


def test_build_messages_includes_intent_guide():
    msgs = build_messages(
        paipan=_SAMPLE_PAIPAN, history=[],
        user_message="今年运气", intent="timing", retrieved=[],
    )
    assert "【本轮：时机/大运流年】" in msgs[0]["content"]


def test_build_messages_includes_docs_bazi_output_style():
    msgs = build_messages(
        paipan=_SAMPLE_PAIPAN, history=[],
        user_message="今年我适合换工作吗",
        intent="career", retrieved=[],
    )
    sys = msgs[0]["content"]
    assert "【输出风格预设 — 对齐 docs/bazi-analysis §0】" in sys
    assert "像一个懂命理的朋友在聊天" in sys
    assert "内部 checklist" in sys
    assert "不要把结论都包成 A/B/C 标签" in sys


def test_relationship_prompt_enforces_gender_specific_spouse_star_language():
    msgs = build_messages(
        paipan={
            **_SAMPLE_PAIPAN,
            "gender": "female",
            "birthInput": {"gender": "female"},
        },
        history=[],
        user_message="帮我看正缘",
        intent="relationship",
        retrieved=[],
    )
    sys = msgs[0]["content"]

    assert "女命看感情" in sys
    assert "官杀/夫星" in sys
    assert "男命看感情" in sys
    assert "财星/妻星" in sys
    assert "不要把女命的正财/偏财写成妻星或伴侣星" in sys


def test_build_messages_requests_markdown_and_blocks_harsh_fatalistic_language():
    msgs = build_messages(
        paipan=_SAMPLE_PAIPAN,
        history=[],
        user_message="这盘有什么问题",
        intent="other",
        retrieved=[],
    )
    sys = msgs[0]["content"]

    assert "Markdown" in sys
    assert "短段落" in sys
    assert "项目符号" in sys
    assert "避免恐吓式词汇" in sys
    assert "克妻/克夫" in sys
    assert "非贫即夭" in sys


def test_build_messages_does_not_invite_free_classical_quotes():
    msgs = build_messages(
        paipan=_SAMPLE_PAIPAN, history=[],
        user_message="古籍怎么看这盘",
        intent="career", retrieved=[],
    )
    sys = msgs[0]["content"]
    assert "只引用本请求提供的古籍原文锚点" in sys
    assert "训练数据中的任何原文都可自由引用" not in sys
    assert "直接引用即可" not in sys


def test_fallback_style_present():
    assert isinstance(FALLBACK_STYLE, str)
    assert len(FALLBACK_STYLE) > 50
