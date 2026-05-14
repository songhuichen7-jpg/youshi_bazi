"""classics_polisher persona pool — JSON parser + structural acceptance."""
from __future__ import annotations

import json

from app.services.classics_polisher import _parse_persona_item


_RAW_HIT = {
    "source": "滴天髓·性情",
    "scope": "六亲论·性情",
    "text": "甲子日元，生于孟春，木当令而不太过，火居相位不烈……为人不苟，无骄谄刻薄之行，有廉恭仁厚之风。",
    "_tier": "case",
}


def test_parse_persona_item_happy_path():
    payload = json.dumps({
        "id": "0",
        "quote": "甲子日元，生于孟春，木当令而不太过，火居相位不烈。为人不苟，无骄谄刻薄之行。",
        "plain": "木火相位，五行中和；为人不苟、廉恭仁厚。",
        "fit_note": "日干甲、月令寅、建禄当令，与命例同型。",
        "tier": "case",
        "book": "滴天髓",
        "chapter": "性情",
        "section": "命例 1",
    })
    item = _parse_persona_item(payload, [_RAW_HIT])
    assert item is not None
    assert item["tier"] == "case"
    assert item["book"] == "滴天髓"
    assert "甲子日元" in item["quote"]
    assert item["section"] == "命例 1"


def test_parse_persona_item_drops_when_quote_not_in_raw():
    """LLM 自创原文 → 拒绝。"""
    payload = json.dumps({
        "id": "0",
        "quote": "此盘日干甲，性情温厚有度，处事中正不偏，乃人间正气也。",  # 不在原文里
        "plain": "白话",
        "fit_note": "日干甲。",
        "tier": "case",
        "book": "滴天髓", "chapter": "性情",
    })
    assert _parse_persona_item(payload, [_RAW_HIT]) is None


def test_parse_persona_item_drops_when_plain_or_fit_note_missing():
    payload = json.dumps({
        "id": "0",
        "quote": "甲子日元，生于孟春，木当令而不太过。",
        "plain": "",
        "fit_note": "日干甲。",
        "tier": "case", "book": "滴天髓", "chapter": "性情",
    })
    assert _parse_persona_item(payload, [_RAW_HIT]) is None


def test_parse_persona_item_returns_none_on_id_null():
    """LLM 表示候选都不贴 → null。"""
    payload = json.dumps({"id": None})
    assert _parse_persona_item(payload, [_RAW_HIT]) is None


def test_parse_persona_item_invalid_tier_falls_back_to_raw_tier():
    payload = json.dumps({
        "id": "0",
        "quote": "甲子日元，生于孟春，木当令而不太过。",
        "plain": "白话",
        "fit_note": "日干甲、月令寅。",
        "tier": "weird",
        "book": "滴天髓", "chapter": "性情",
    })
    item = _parse_persona_item(payload, [_RAW_HIT])
    assert item is not None
    assert item["tier"] == "case"  # 退到 raw["_tier"]


def test_parse_persona_item_converts_traditional_to_simplified():
    """繁体输入 — 系统应自动转简体（_quote_belongs_to_raw 用 _compact_for_match
    做归一比对，所以繁体 quote 也能通过校验）。"""
    raw = {
        "source": "三命通会",
        "scope": "卷四",
        "text": "甲日申月為偏官喜身旺合制忌身弱",
        "_tier": "general",
    }
    payload = json.dumps({
        "id": "0",
        "quote": "甲日申月為偏官，喜身旺合制，忌身弱。",  # 繁体 + 加了标点
        "plain": "甲日生於申月，本地是七杀格，宜身旺得制忌身弱。",
        "fit_note": "日干甲、月令申、七杀、身弱。",
        "tier": "general",
        "book": "三命通會",
        "chapter": "卷四",
    })
    item = _parse_persona_item(payload, [raw])
    assert item is not None
    # 繁→简 已应用 — 输出无繁体异体字
    assert "為" not in item["quote"]
    assert "为" in item["quote"]
    assert "三命通会" == item["book"]


def test_parse_persona_item_drops_solo_extreme_quote():
    """persona pool 现在跟 verdict 一样过滤极端凶词；
    选了"災夭"这种孤立凶词的 quote 应该被拒。"""
    raw = {
        "source": "三命通会",
        "scope": "卷五",
        "text": "甲生丑月變官為鬼旺處必傾多致災夭",
        "_tier": "general",
    }
    payload = json.dumps({
        "id": "0",
        "quote": "變官為鬼，旺處必傾，多致災夭。",  # 含夭, 无制化
        "plain": "白话",
        "fit_note": "日干甲、月令申、七杀。",
        "tier": "general",
        "book": "三命通会", "chapter": "卷五",
    })
    assert _parse_persona_item(payload, [raw]) is None


def test_parse_persona_item_keeps_extreme_with_remedy():
    """带制化语境的极端凶词 — 应放行（七杀 + 化煞 是技术词搭配）。"""
    raw = {
        "source": "三命通会",
        "scope": "论偏官",
        "text": "杀重身轻得印化煞则贵不致夭折",
        "_tier": "general",
    }
    payload = json.dumps({
        "id": "0",
        "quote": "杀重身轻，得印化煞则贵，不致夭折。",
        "plain": "白话",
        "fit_note": "七杀重，得印化煞。",
        "tier": "general",
        "book": "三命通会", "chapter": "论偏官",
    })
    item = _parse_persona_item(payload, [raw])
    assert item is not None
    assert "化煞" in item["quote"]


def test_parse_persona_item_accepts_unpunctuated_long_quote():
    """v12+ 不再在 parse 阶段拒收无标点 quote — 古籍 corpus 的 三命通会
    cluster-style 段落原文就无断句, LLM 在 temp=0 下倾向直接照抄,
    parse 阶段拒收会导致整个面板空态。

    v12 行为: parse 接受无标点 quote, 由 _polish_persona 调 fast tier
    LLM 后处理补标点 (失败也比空态强)。"""
    raw = {
        "source": "三命通会", "scope": "卷四",
        "text": "甲日申月為偏官喜身旺合制忌身弱正官運亦然尤忌再見七杀",
        "_tier": "general",
    }
    payload = json.dumps({
        "id": "0",
        "quote": "甲日申月為偏官喜身旺合制忌身弱正官運亦然尤忌再見七杀",
        "plain": "白话",
        "fit_note": "日干甲、月令申。",
        "tier": "general",
        "book": "三命通会", "chapter": "卷四",
    })
    item = _parse_persona_item(payload, [raw])
    assert item is not None
    assert "甲日申月" in item["quote"]


def test_parse_persona_item_short_quote_skips_punctuation_check():
    raw = {
        "source": "三命通会", "scope": "卷四",
        "text": "甲日申月為偏官喜身旺合制忌身弱",
        "_tier": "general",
    }
    payload = json.dumps({
        "id": "0",
        "quote": "甲日申月為偏官喜身旺合制忌身弱",
        "plain": "你的命格是被外部压力推着走的人",
        "fit_note": "日干甲、月令申。",
        "tier": "general",
        "book": "三命通会", "chapter": "卷四",
    })
    item = _parse_persona_item(payload, [raw])
    assert item is not None


def test_parse_persona_item_accepts_ocr_confusable_correction():
    """LLM "纠正" 巳→已 是 OCR 易混字 (古籍扫描常见缺陷), 不应拒收。"""
    raw = {
        "source": "三命通会",
        "scope": "卷五",
        "text": "甲生丑月内有辛金又值酉时巳是重犯若天干透辛多更行西方力不勝任變官為鬼旺處必傾多致灾夭須有合制方吉",
        "_tier": "general",
    }
    payload = json.dumps({
        "id": "0",
        # 注意 巳 → 已 (LLM 自动"纠错"); 应该被 OCR fold 接受
        "quote": "甲生丑月内有辛金，又值酉时已是重犯，若天干透辛多，更行西方，力不胜任，变官为鬼，旺处必倾，多致灾夭，须有合制方吉。",
        "plain": "你这个人底子里有金的克制压力，金气如果太重又来运，就容易招麻烦，需要化解的力量。",
        "fit_note": "日干甲、月令丑，金重论甲生丑月。",
        "tier": "general",
        "book": "三命通会", "chapter": "卷五",
    })
    item = _parse_persona_item(payload, [raw])
    assert item is not None
    assert "已是重犯" in item["quote"]  # 显示用 LLM 的版本 (繁→简 + 标点)


def test_parse_persona_item_accepts_v12_ocr_variants():
    """v12 扩展的 OCR fold 表覆盖 三命通会 corpus 高频变体: 㑹→会, 㸔→看,
    㓙→凶, 湏→须, 歳→岁。LLM 在加标点 + "纠错"时常顺手把这些变体改成
    现代标准字; provenance 校验须能识别为同字。"""
    raw = {
        "source": "三命通会",
        "scope": "卷五",
        "text": "透火制地支子辰㑹印成局则杀生印印生身作权贵㸔年干露杀为㓙尤甚湏看歳君",
        "_tier": "general",
    }
    payload = json.dumps({
        "id": "0",
        # 全部变体 → canonical: 㑹→会, 㸔→看, 㓙→凶, 湏→须, 歳→岁
        "quote": "透火制地支子辰会印成局，则杀生印，印生身，作权贵看。年干露杀，为凶尤甚，须看岁君。",
        "plain": "讲的是七杀的吉凶处理 — 七杀（外部压力）若有火制约且地支成印局，能化为权贵；若年干透杀又逢金旺，要看岁运。",
        "fit_note": "日干甲、月令申、七杀格、用神丁火。",
        "tier": "general",
        "book": "三命通会", "chapter": "卷五",
    })
    item = _parse_persona_item(payload, [raw])
    assert item is not None, "v12 OCR fold should accept this LLM correction"
    assert "权贵看" in item["quote"]


def test_punctuate_drift_ratio_within_tolerance():
    """加标点 LLM 顺手做 OCR 修正 (㑹→会, 㸔→看, 㓙→凶) 这些少量字符变更
    应该被 drift 容差判为"等价", 让我们采用更可读的版本。"""
    from app.services.classics_polisher import (
        _quote_punctuate_drift_ratio,
        _MAX_PUNCTUATE_DRIFT,
    )
    original = "透火制地支子辰㑹印成局则杀生印印生身作权贵㸔年干露杀为㓙尤甚"
    punctuated = "透火制地支子辰会印成局，则杀生印，印生身，作权贵看。年干露杀，为凶尤甚。"
    drift = _quote_punctuate_drift_ratio(original, punctuated)
    assert drift <= _MAX_PUNCTUATE_DRIFT, (
        f"OCR-only corrections ({drift:.2%}) should be within tolerance "
        f"({_MAX_PUNCTUATE_DRIFT:.0%})"
    )


def test_punctuate_drift_ratio_rejects_real_rewrite():
    """LLM 如果不只是加标点而真的改写内容, drift 必须超阈值, 触发回退原文。"""
    from app.services.classics_polisher import (
        _quote_punctuate_drift_ratio,
        _MAX_PUNCTUATE_DRIFT,
    )
    original = "甲日申月為偏官喜身旺合制忌身弱正官運亦然尤忌再見七杀"
    rewritten = "甲日生在申月就是七杀格，要身体强壮，最怕身弱再撞官杀。"
    drift = _quote_punctuate_drift_ratio(original, rewritten)
    assert drift > _MAX_PUNCTUATE_DRIFT, (
        f"actual rewrite ({drift:.2%}) must exceed tolerance "
        f"({_MAX_PUNCTUATE_DRIFT:.0%})"
    )
