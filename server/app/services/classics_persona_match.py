"""Pure structural pre-filter for the 古书定调 persona pool.

Given a candidate classical-text claim and a paipan dict, classify the
claim into one of three tiers:

* ``"case"``    — the text references a *specific* 命例 whose 日干 + 月支
                   match this paipan (e.g. "甲子日元，生于孟春…").
* ``"general"`` — the text is a 论 X 通用判文 whose 日干 OR 主格局 matches
                   (e.g. "论甲日生人…" / "凡建禄格者…"). No specific 命例.
* ``"no-match"``— neither. The claim should be dropped before LLM polish.

This runs *before* any LLM call so structurally-irrelevant material never
makes it into the prompt context. Pure function — no I/O, no LLM, fast.
"""
from __future__ import annotations

import re
from typing import Literal

Tier = Literal["case", "general", "no-match"]

_MONTH_NAME_BY_ZHI: dict[str, tuple[str, ...]] = {
    "寅": ("孟春", "正月", "寅月"),
    "卯": ("仲春", "二月", "卯月"),
    "辰": ("季春", "三月", "辰月"),
    "巳": ("孟夏", "四月", "巳月"),
    "午": ("仲夏", "五月", "午月"),
    "未": ("季夏", "六月", "未月"),
    "申": ("孟秋", "七月", "申月"),
    "酉": ("仲秋", "八月", "酉月"),
    "戌": ("季秋", "九月", "戌月"),
    "亥": ("孟冬", "十月", "亥月"),
    "子": ("仲冬", "十一月", "子月"),
    "丑": ("季冬", "十二月", "丑月"),
}

_TEN_GANS = "甲乙丙丁戊己庚辛壬癸"


def _day_gan(paipan: dict) -> str:
    rizhu = str(paipan.get("rizhu") or "")
    if rizhu and rizhu[0] in _TEN_GANS:
        return rizhu[0]
    sizhu = paipan.get("sizhu") or {}
    day = str(sizhu.get("day") or "") if isinstance(sizhu, dict) else ""
    return day[0] if day and day[0] in _TEN_GANS else ""


def _month_zhi(paipan: dict) -> str:
    sizhu = paipan.get("sizhu") or {}
    month = str(sizhu.get("month") or "") if isinstance(sizhu, dict) else ""
    return month[1] if len(month) >= 2 else ""


def _main_geju(paipan: dict) -> str:
    geju = paipan.get("geJu") or paipan.get("ge_ju") or {}
    if isinstance(geju, dict):
        cand = geju.get("mainCandidate") or geju.get("main_candidate") or {}
        if isinstance(cand, dict):
            name = str(cand.get("shishen") or cand.get("name") or "").strip()
            if name:
                return name
    raw = str(paipan.get("geju") or "")
    return raw.removesuffix("格").strip()


def is_structural_match(text: str, paipan: dict) -> Tier:
    if not text or not paipan:
        return "no-match"

    day_gan = _day_gan(paipan)
    month_zhi = _month_zhi(paipan)
    main_geju = _main_geju(paipan)

    # ── 1. case tier — 具体命例 ──────────────────────────────────────
    # 模式 A: "X日元，生于 Y月" / "X日元，生 Y月"
    # 模式 B: "X日生于 Y月"
    if day_gan and month_zhi:
        month_terms = "|".join(re.escape(m) for m in _MONTH_NAME_BY_ZHI.get(month_zhi, ()))
        if month_terms:
            patterns = [
                rf"{day_gan}\w?日元[，,]?\s*生于\s*({month_terms})",
                rf"{day_gan}\w?日元[，,]?\s*生\s*({month_terms})",
                rf"{day_gan}日\s*生于\s*({month_terms})",
            ]
            for pat in patterns:
                if re.search(pat, text):
                    return "case"

    # ── 2. no-match — 别人盘的具体命例 ────────────────────────────────
    # 文本含 "<其他日干>日元，生于..." 标记 → 是别人盘的命例，与本盘无关。
    # general 段落不会带这个具体命例标记，所以这里安全 drop。
    if day_gan:
        other_gans = [g for g in _TEN_GANS if g != day_gan]
        for g in other_gans:
            if re.search(rf"{g}\w?日元[，,]?\s*生于", text):
                return "no-match"

    # ── 3. general tier — 信任 retrieval pool 章节白名单 ──────────────
    # 检索 policy 已经把 domain + chapter 筛过；走到这里都是性情/论性情/
    # 论X日/论X格 类章节。只要文本里出现本盘 day_gan 或主格局名 → general
    # （让 LLM 在 prompt 里做更细的相关度判断）。
    if (day_gan and day_gan in text) or (main_geju and main_geju in text):
        return "general"

    # ── 4. fallback no-match — 文本既无本盘 day_gan 也无主格局 ──────
    # 哪怕来自合规章节，与本盘要素完全无关时仍 drop。
    return "no-match"


__all__ = ["Tier", "is_structural_match"]
