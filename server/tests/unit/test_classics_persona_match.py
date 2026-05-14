"""classics_persona_match — 给一段古籍命例 + 本盘，判定结构匹配档次。

tier="case" — 命例的"X日元 + 生于Y月"明确命中
tier="general" — "论X日生人" / "论X格" 之类的通用论文，与日干/月令/格局有命中
tier="no-match" — 都对不上
"""
from __future__ import annotations

from app.services.classics_persona_match import is_structural_match


def _paipan(*, day_gan="甲", month_zhi="寅", main_geju="建禄", strength="身强"):
    return {
        "rizhu": f"{day_gan}子",  # 简化：日柱 = 日干 + 子
        "sizhu": {
            "year": "丙申", "month": f"丙{month_zhi}",
            "day": f"{day_gan}子", "hour": "甲戌",
        },
        "geju": main_geju + "格",
        "geJu": {"mainCandidate": {"shishen": main_geju}},
        "dayStrength": strength,
    }


def test_case_tier_when_exact_day_month_match():
    paipan = _paipan(day_gan="甲", month_zhi="寅")
    text = "甲子日元，生于孟春，木当令而不太过……为人不苟，无骄谄刻薄之行。"
    assert is_structural_match(text, paipan) == "case"


def test_case_tier_handles_alternate_phrasing():
    """命例文里"X日生于Y月"是另一种常见写法，不带"日元"。"""
    paipan = _paipan(day_gan="庚", month_zhi="亥")
    text = "庚日生于亥月，金水相涵，性情沉静而有谋略。"
    assert is_structural_match(text, paipan) == "case"


def test_general_tier_when_only_pattern_matches():
    """《论建禄格》/《论甲日生人》总论段落 — 没具体命例，但题目对得上。"""
    paipan = _paipan(day_gan="甲", main_geju="建禄")
    text = "凡建禄格者，须看月令所透为用。透官则贵，透财则富，透杀则要制化。"
    assert is_structural_match(text, paipan) == "general"


def test_general_tier_when_only_day_gan_matches():
    paipan = _paipan(day_gan="甲")
    text = "论甲日生人：甲为栋梁之木，性情仁厚，逢秋则凋，得水滋而清秀。"
    assert is_structural_match(text, paipan) == "general"


def test_general_tier_when_day_gan_appears_mid_sentence():
    """实际 retrieval 命中常见情况：文本不带 '论甲日' 标准前缀，
    但 day_gan 在文本里出现（章节已被 retrieval policy 白名单筛过）。"""
    paipan = _paipan(day_gan="甲")
    text = "建禄者乃甲日寅月乙日卯月五行临官之位也，甲用金为官，金绝在寅。"
    assert is_structural_match(text, paipan) == "general"


def test_general_tier_when_main_geju_mentioned_without_day_gan():
    """day_gan 没在文本里出现，但主格局名出现 → general（章节命中本盘格局
    类型，仍是有用的讨论）。"""
    paipan = _paipan(main_geju="建禄", day_gan="丁")  # 丁不在下文
    text = "建禄者须看月令所透为用，透官则贵，透财则富。"
    assert is_structural_match(text, paipan) == "general"


def test_no_match_when_day_gan_collides():
    """命例写的是丙日盘，本盘是甲日 — 完全对不上。"""
    paipan = _paipan(day_gan="甲", month_zhi="寅")
    text = "丙午日元，生于仲夏，火炎土燥……"
    assert is_structural_match(text, paipan) == "no-match"


def test_no_match_when_unrelated_topic():
    paipan = _paipan(day_gan="甲", month_zhi="寅")
    text = "论女命：女命以官星为夫，财星为父母。"
    assert is_structural_match(text, paipan) == "no-match"


def test_robust_to_missing_paipan_fields():
    """paipan 字段不全时不应抛异常 — 没法判时退到 no-match。"""
    assert is_structural_match("任意文本", {}) == "no-match"
    assert is_structural_match("", {"rizhu": "甲子"}) == "no-match"
