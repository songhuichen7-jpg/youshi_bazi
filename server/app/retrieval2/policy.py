"""Intent-specific retrieval policy.

BM25 and KG are intentionally generic. This module adds a small amount of
domain judgment: which books/chapters are authoritative for each question
type, and which neighboring topics should be kept out of the selector pool.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .types import ClaimTags, ClaimUnit


# chunk_type → boost adjustment. Applied after domain / file / axis boosts
# so structural論述总能压过同 domain 的"必贫必夭"或单纯神煞列举。
#
# 设计取舍 (vs 直接 reject):
# - 不直接 reject. 三命通会 "妻得位则子嗣昌" 这类 judgement 仍带 domain
#   信号, selector 可以用; reject 会一刀切。
# - 但 -0.6 / -0.4 已经够把 judgement / shensha 推出 top-N — 在
#   _fuse(policy weight=1.35) 下相当于减掉 ~半档 KG/policy 通道。
# - meta / unclear → 给一个保守降权(-0.3)而非 reject, 防止极少数
#   误标的有用条目被全删。
_KIND_BOOST: dict[str, float] = {
    "principle": 0.0,
    "rule":      0.0,   # rule 与 principle 同权, 都是结构论述
    "case":      0.0,   # case 信号有用 (尤其 persona / 命例匹配), 不降权
    "formula":   -0.05, # 诀文有信号但密度高, 微降一档让结构论述优先
    "heuristic": -0.05,
    "judgement": -0.6,  # 绝对断语降权, 除非已被 domain 高亮强抵消
    "shensha":   -0.4,  # 神煞辅助, 主结构没缺时不要它霸占名额
    "meta":      -0.3,
    "unclear":   -0.3,
}


def _kind_for(claim: ClaimUnit, tags: ClaimTags) -> str:
    """Prefer LLM-refined_kind over splitter heuristic. Falls back to
    splitter kind when tagger ran with v1 vocab and didn't see the new
    judgement/shensha values (refined_kind defaults to 'principle')."""
    refined = tags.refined_kind
    # LLM tagger v1 default 是 "principle". 只有当 splitter 已经识别为
    # 非 principle 时, 我们才优先用 splitter 结果作为更强信号 (反之 v2+
    # 的 tagger 会把 splitter 漏掉的 judgement/shensha 主动挑出, 走
    # refined 路径)
    if refined == "principle" and claim.kind != "principle":
        return claim.kind
    return refined


@dataclass(frozen=True, slots=True)
class RetrievalPolicy:
    kind: str
    positive_domains: tuple[str, ...] = ()
    preferred_books: tuple[str, ...] = ()
    allowed_file_fragments: tuple[str, ...] = ()
    preferred_files: tuple[str, ...] = ()
    preferred_file_fragments: tuple[str, ...] = ()
    rejected_file_fragments: tuple[str, ...] = ()
    required_domains: tuple[str, ...] = ()
    required_terms: tuple[str, ...] = ()
    day_gan: str = ""
    month_zhi: str = ""
    season: str = ""
    strict_chart_axis: bool = False
    selector_hint: str = ""
    term_boosts: tuple[str, ...] = field(default_factory=tuple)
    kind_boost: dict[str, float] = field(default_factory=lambda: dict(_KIND_BOOST))

    def rejects(self, claim: ClaimUnit, tags: ClaimTags) -> bool:
        file_name = claim.chapter_file
        if self.allowed_file_fragments and not any(
            fragment in file_name for fragment in self.allowed_file_fragments
        ):
            return True
        if any(fragment in file_name for fragment in self.rejected_file_fragments):
            return True
        if self.strict_chart_axis:
            if self.day_gan and tags.day_gan and self.day_gan not in tags.day_gan:
                return True
            if self.month_zhi and tags.month_zhi and self.month_zhi not in tags.month_zhi:
                return True
            if self.season and tags.season and self.season not in tags.season:
                return True
        if self.required_domains or self.required_terms:
            text = claim.text + claim.chapter_title + (claim.section or "")
            has_domain = bool(set(tags.domain) & set(self.required_domains))
            has_term = any(term in text for term in self.required_terms)
            if not has_domain and not has_term:
                return True
        return False

    def boost(self, claim: ClaimUnit, tags: ClaimTags) -> float:
        if self.rejects(claim, tags):
            return -1.0

        score = 0.0
        if claim.book in self.preferred_books:
            score += 0.25
        if claim.chapter_file in self.preferred_files:
            score += 1.25
        if any(fragment in claim.chapter_file for fragment in self.preferred_file_fragments):
            score += 0.8
        if self.positive_domains and set(tags.domain) & set(self.positive_domains):
            score += 0.65
        if self.day_gan and self.day_gan in tags.day_gan:
            score += 1.25
        if self.day_gan and self.day_gan in (claim.chapter_title + claim.chapter_file + (claim.section or "")):
            score += 0.85
        if self.month_zhi and self.month_zhi in tags.month_zhi:
            score += 0.55
        if self.season and self.season in tags.season:
            score += 0.35
        if self.day_gan and self.month_zhi and self.day_gan in tags.day_gan and self.month_zhi in tags.month_zhi:
            score += 1.1
        if self.term_boosts:
            text = claim.text + claim.chapter_title + (claim.section or "")
            score += 0.2 * sum(1 for term in self.term_boosts if term in text)

        # chunk_type adjust: judgement / shensha 降权,principle 不动。
        # 在所有 domain / file / axis boost 之后施加,这样即便 judgement
        # 落在 preferred_files 里也仍然被压制。
        kind = _kind_for(claim, tags)
        score += self.kind_boost.get(kind, 0.0)
        return score


def _paipan(chart: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(chart, dict):
        return {}
    return chart.get("PAIPAN") or chart


_GENDER_MALE = frozenset(("m", "male", "男", "男命", "1"))
_GENDER_FEMALE = frozenset(("f", "female", "女", "女命", "0", "2"))


def _gender(chart: dict[str, Any]) -> str:
    """Returns 'male' / 'female' / ''. Reads from top-level ``gender`` or
    ``birthInput.gender`` / ``birth_input.gender`` (matches paipan compute
    output and frontend FormScreen payload)."""
    p = _paipan(chart)
    raw = str(p.get("gender") or "")
    if not raw:
        bi = p.get("birthInput") or p.get("birth_input") or {}
        if isinstance(bi, dict):
            raw = str(bi.get("gender") or "")
    raw = raw.strip().lower()
    if raw in _GENDER_MALE:
        return "male"
    if raw in _GENDER_FEMALE:
        return "female"
    return ""


def _day_gan(chart: dict[str, Any]) -> str:
    p = _paipan(chart)
    meta = p.get("META") or {}
    rizhu = str(meta.get("rizhuGan") or p.get("rizhu") or "")
    if rizhu:
        return rizhu[0]
    sizhu = p.get("sizhu") or {}
    day = str(sizhu.get("day") or "") if isinstance(sizhu, dict) else ""
    return day[:1] if day else ""


def _month_zhi(chart: dict[str, Any]) -> str:
    sizhu = _paipan(chart).get("sizhu") or {}
    month = str(sizhu.get("month") or "") if isinstance(sizhu, dict) else ""
    return month[1:2] if len(month) >= 2 else ""


def _season(chart: dict[str, Any]) -> str:
    return {
        "寅": "春", "卯": "春", "辰": "春",
        "巳": "夏", "午": "夏", "未": "夏",
        "申": "秋", "酉": "秋", "戌": "秋",
        "亥": "冬", "子": "冬", "丑": "冬",
    }.get(_month_zhi(chart), "")


def _main_shishen(chart: dict[str, Any]) -> str:
    p = _paipan(chart)
    geju = p.get("geJu") or p.get("ge_ju") or {}
    main = (
        (geju.get("mainCandidate") if isinstance(geju, dict) else None)
        or (geju.get("main_candidate") if isinstance(geju, dict) else None)
        or {}
    )
    text = ""
    if isinstance(main, dict):
        text = str(main.get("shishen") or main.get("name") or "")
    text = text or str(p.get("geju") or "")
    if "偏官" in text or "七杀" in text or "七煞" in text:
        return "七杀"
    if "正官" in text:
        return "正官"
    if "财" in text:
        return "正财"
    if "印" in text:
        return "正印"
    return ""


def _day_strength(chart: dict[str, Any]) -> str:
    raw = str(_paipan(chart).get("dayStrength") or "")
    if "弱" in raw or "衰" in raw or "轻" in raw:
        return "身弱"
    if "强" in raw or "旺" in raw:
        return "身强"
    return raw


def _yongshen_terms(chart: dict[str, Any]) -> tuple[str, ...]:
    p = _paipan(chart)
    out: list[str] = []
    if p.get("yongshen"):
        out.append(str(p.get("yongshen")))
    detail = p.get("yongshenDetail") or {}
    if isinstance(detail, dict):
        primary = detail.get("primary")
        if primary:
            out.append(str(primary))
        for cand in detail.get("candidates") or []:
            if isinstance(cand, dict) and cand.get("name"):
                out.append(str(cand.get("name")))
    return tuple(dict.fromkeys(t for t in out if t))


def _yongshen_school_diverged(chart: dict[str, Any]) -> bool:
    """True iff the chart's yongshenDetail.warnings indicates a 调候 vs 格局
    用神 split. paipan engine produces these warnings via compose_yongshen
    when 调候 法 and 格局 法 disagree on the primary yongshen ("调候用神
    与格局用神不同 — 古籍两派各有取法"). We surface the divergence to
    the selector_hint so the LLM can frame the output as a school
    comparison instead of picking one side silently."""
    detail = (_paipan(chart) or {}).get("yongshenDetail") or {}
    if not isinstance(detail, dict):
        return False
    warnings = detail.get("warnings") or []
    if not isinstance(warnings, list):
        return False
    patterns = ("两派", "流派", "古籍两", "调候 != 格局")
    return any(
        isinstance(w, str) and any(p in w for p in patterns)
        for w in warnings
    )


_QIONGTONG_BY_DAY_GAN = {
    "甲": "qiongtong-baojian/02_lun-jia-mu",
    "乙": "qiongtong-baojian/03_lun-yi-mu",
    "丙": "qiongtong-baojian/04_lun-bing-huo",
    "丁": "qiongtong-baojian/05_lun-ding-huo",
    "戊": "qiongtong-baojian/06_lun-wu-tu",
    "己": "qiongtong-baojian/07_lun-ji-tu",
    "庚": "qiongtong-baojian/08_lun-geng-jin",
    "辛": "qiongtong-baojian/09_lun-xin-jin",
    "壬": "qiongtong-baojian/10_lun-ren-shui",
    "癸": "qiongtong-baojian/11_lun-gui-shui",
}


# 主十神 → 章节路由表. Key 为规范化十神名 (输入会先被 _main_shishen
# 通过 normalize 收敛到 正官 / 七杀 / 正财 / 正印 / 正官 等).
# allowed: 不会被 reject 掉的章节;preferred: 排序时强加权;
# terms: term_boosts 里要命中的关键词;hint: selector LLM 提示。
_MAIN_SHISHEN_CHAPTERS: dict[str, dict[str, tuple[str, ...] | str]] = {
    "正官": {
        "allowed": (
            "ziping-zhenquan/31_lun-zheng-guan",
            "ziping-zhenquan/32_lun-zheng-guan-qu-yun",
            "ditian-sui/tong-shen-lun_21_guan-sha",
            "yuanhai-ziping/07_shi-shen_zheng-guan-pian-guan",
        ),
        "preferred": (
            "ziping-zhenquan/31_lun-zheng-guan.md",
            "ziping-zhenquan/32_lun-zheng-guan-qu-yun.md",
            "ditian-sui/tong-shen-lun_21_guan-sha.md",
        ),
        "terms": ("正官", "官星", "官印", "官清", "财官", "官杀混杂"),
        "hint": (
            "正官格总览:优先选正官原文、正官取运、官杀章 + 渊海正官篇;"
            "重点看清纯/混杂/有无伤官刑冲;不要选别的格局通论。"
        ),
    },
    "七杀": {
        "allowed": (
            "ziping-zhenquan/39_lun-pian-guan",
            "ziping-zhenquan/40_lun-pian-guan-qu-yun",
            "ditian-sui/tong-shen-lun_21_guan-sha",
            "yuanhai-ziping/07_shi-shen_zheng-guan-pian-guan",
        ),
        "preferred": (
            "ziping-zhenquan/39_lun-pian-guan.md",
            "ziping-zhenquan/40_lun-pian-guan-qu-yun.md",
            "ditian-sui/tong-shen-lun_21_guan-sha.md",
        ),
        "terms": (
            "偏官", "七杀", "七煞", "制杀", "化杀",
            "杀重身轻", "财生杀", "杀印", "食制杀",
        ),
        "hint": (
            "七杀格总览:优先选偏官原文、偏官取运、官杀章 + 制化办法;"
            "身弱杀重时 印化杀 / 食制杀 是核心方法。"
        ),
    },
    "正财": {
        "allowed": (
            "ziping-zhenquan/33_lun-cai",
            "ziping-zhenquan/34_lun-cai-qu-yun",
            "ditian-sui/liu-qin-lun_05_he-zhi-zhang",
            "yuanhai-ziping/06_shi-shen_zheng-cai-pian-cai",
        ),
        "preferred": (
            "ziping-zhenquan/33_lun-cai.md",
            "ziping-zhenquan/34_lun-cai-qu-yun.md",
            "ditian-sui/liu-qin-lun_05_he-zhi-zhang.md",
        ),
        "terms": ("正财", "偏财", "财格", "财气", "财星", "妻财", "食伤生财"),
        "hint": (
            "财格总览:优先选论财、论财取运、何知章、渊海正偏财篇;"
            "看身能否任财、有无食伤通门户。"
        ),
    },
    "偏财": {  # 同 正财
        "allowed": (
            "ziping-zhenquan/33_lun-cai",
            "ziping-zhenquan/34_lun-cai-qu-yun",
            "ditian-sui/liu-qin-lun_05_he-zhi-zhang",
            "yuanhai-ziping/06_shi-shen_zheng-cai-pian-cai",
        ),
        "preferred": (
            "ziping-zhenquan/33_lun-cai.md",
            "ziping-zhenquan/34_lun-cai-qu-yun.md",
            "ditian-sui/liu-qin-lun_05_he-zhi-zhang.md",
        ),
        "terms": ("偏财", "正财", "财格", "财气", "财星", "众人之财", "时上偏财"),
        "hint": (
            "偏财格总览:优先选论财、论财取运、何知章;"
            "时上偏财、众人之财是关键象义。"
        ),
    },
    "正印": {
        "allowed": (
            "ziping-zhenquan/35_lun-yin-shou",
            "ziping-zhenquan/36_lun-yin-shou-qu-yun",
            "yuanhai-ziping/08_shi-shen_yin-shou-dao-shi-jie-cai",
        ),
        "preferred": (
            "ziping-zhenquan/35_lun-yin-shou.md",
            "ziping-zhenquan/36_lun-yin-shou-qu-yun.md",
        ),
        "terms": ("印", "正印", "印绶", "官印相生", "杀印相生", "枭印夺食"),
        "hint": (
            "印绶格总览:优先选论印绶、论印绶取运、渊海印绶篇;"
            "看官印 / 杀印 / 财坏印的结构。"
        ),
    },
    "偏印": {  # 印格通用,但 selector 需识别枭印特性
        "allowed": (
            "ziping-zhenquan/35_lun-yin-shou",
            "ziping-zhenquan/36_lun-yin-shou-qu-yun",
            "yuanhai-ziping/08_shi-shen_yin-shou-dao-shi-jie-cai",
        ),
        "preferred": (
            "ziping-zhenquan/35_lun-yin-shou.md",
            "ziping-zhenquan/36_lun-yin-shou-qu-yun.md",
        ),
        "terms": ("偏印", "印绶", "枭神", "枭印", "倒食"),
        "hint": (
            "偏印格总览:优先选论印绶、论印绶取运;"
            "重点看枭印夺食 / 偏印有无救应。"
        ),
    },
    "食神": {
        "allowed": (
            "ziping-zhenquan/37_lun-shi-shen",
            "ziping-zhenquan/38_lun-shi-shen-qu-yun",
        ),
        "preferred": (
            "ziping-zhenquan/37_lun-shi-shen.md",
            "ziping-zhenquan/38_lun-shi-shen-qu-yun.md",
        ),
        "terms": ("食神", "食神生财", "食制杀", "食伤生财"),
        "hint": (
            "食神格总览:优先选论食神、论食神取运;"
            "重点看食神生财、食制杀、枭神夺食。"
        ),
    },
    "伤官": {
        "allowed": (
            "ziping-zhenquan/41_lun-shang-guan",
            "ziping-zhenquan/42_lun-shang-guan-qu-yun",
            "ditian-sui/tong-shen-lun_22_shang-guan",
            "yuanhai-ziping/05_shi-shen_shang-guan-shi-shen",
        ),
        "preferred": (
            "ziping-zhenquan/41_lun-shang-guan.md",
            "ziping-zhenquan/42_lun-shang-guan-qu-yun.md",
            "ditian-sui/tong-shen-lun_22_shang-guan.md",
        ),
        "terms": ("伤官", "伤官见官", "伤官配印", "伤官生财", "假伤官", "真伤官"),
        "hint": (
            "伤官格总览:优先选论伤官、论伤官取运、滴天髓伤官章;"
            "重点看伤官见官、伤官配印、伤官生财三种结构。"
        ),
    },
}


def _meta_policy_for_main_shishen(
    chart: dict[str, Any], kind: str, main_shishen: str,
) -> RetrievalPolicy | None:
    """Build a meta-intent policy when the chart's main 十神 has a routing
    table entry. Returns None if main_shishen is empty or unmapped (caller
    falls through to default policy)."""
    cfg = _MAIN_SHISHEN_CHAPTERS.get(main_shishen)
    if cfg is None:
        return None

    day_gan = _day_gan(chart)
    month_zhi = _month_zhi(chart)
    month_name = _MONTH_NAME_BY_ZHI.get(month_zhi, "")
    qiongtong_file = _QIONGTONG_BY_DAY_GAN.get(day_gan, "")
    season = _season(chart)

    allowed = (
        (qiongtong_file,) if qiongtong_file else ()
    ) + cfg["allowed"] + (
        # 三命通会 juan-04 / juan-05 论十干 / 论十干生十二月,
        # 是日干 × 月令的散布旁证,任何 主十神 meta 都可用
        "sanming-tonghui/juan-04",
        "sanming-tonghui/juan-05",
    )
    preferred = (
        (f"{qiongtong_file}.md",) if qiongtong_file else ()
    ) + cfg["preferred"] + (
        ("sanming-tonghui/juan-04.md",) if main_shishen in ("七杀", "正官", "正财", "偏财") else ()
    )

    chart_axis_terms = tuple(
        t for t in (
            f"{day_gan}日" if day_gan else "",
            f"{month_zhi}月" if month_zhi else "",
            f"{month_name}{day_gan}" if month_name and day_gan else "",
            month_name,
            _day_strength(chart),
            *_yongshen_terms(chart),
        ) if t
    )

    selector_hint = cfg["hint"]
    if _yongshen_school_diverged(chart):
        # 分歧时,在 hint 末尾追加"两派对照"的明确指令,且把穷通日干
        # 月令章 (调候派核心) 强制塞入 preferred,即使 主十神 routing
        # 表本来不会优先它。
        selector_hint = (
            selector_hint + " 注意:本盘调候用神与格局用神分歧 — "
            "至少各保留一条调候派(穷通宝鉴)和格局派(子平真诠)证据,"
            "便于呈现两派对照,不要只选一派。"
        )
        if qiongtong_file and f"{qiongtong_file}.md" not in preferred:
            preferred = preferred + (f"{qiongtong_file}.md",)

    return RetrievalPolicy(
        kind=kind,
        positive_domains=("格局成败", "用神取舍", "财官", "调候"),
        allowed_file_fragments=allowed,
        preferred_files=preferred,
        day_gan=day_gan,
        month_zhi=month_zhi,
        season=season,
        strict_chart_axis=True,
        selector_hint=selector_hint,
        term_boosts=chart_axis_terms + cfg["terms"],
    )


_MONTH_NAME_BY_ZHI = {
    "寅": "正月", "卯": "二月", "辰": "三月",
    "巳": "四月", "午": "五月", "未": "六月",
    "申": "七月", "酉": "八月", "戌": "九月",
    "亥": "十月", "子": "十一月", "丑": "十二月",
}


def _looks_like_tiaohou(kind: str, user_message: str | None) -> bool:
    text = f"{kind} {user_message or ''}"
    return any(term in text for term in ("调候", "寒暖", "燥湿", "冬天", "夏天", "取暖", "解冻"))


def build_policy(chart: dict[str, Any], kind: str, user_message: str | None = None) -> RetrievalPolicy:
    """Return the ranking policy for one retrieval request.

    NOTE: caller (api/charts.py:316) passes ``kind=f"section:{name}"`` for
    section LLM streams (wealth / relationship / health / etc.), but the
    dispatch logic below matches bare names like "wealth". Without stripping
    the prefix, **every section retrieval falls back to bare BM25+KG with
    no domain filtering** — caught by 4 failing tests + reproducible on the
    prod index. Strip once at entry so all sub-policies see the canonical
    name. ``kind`` field on the returned policy keeps the original value
    for telemetry / selector hint context.
    """
    dispatch_kind = kind.removeprefix("section:") if kind.startswith("section:") else kind
    if _looks_like_tiaohou(kind, user_message):
        return RetrievalPolicy(
            kind=kind,
            positive_domains=("调候", "用神取舍"),
            preferred_books=("qiongtong-baojian",),
            allowed_file_fragments=("qiongtong-baojian/", "han-nuan", "zao-shi"),
            preferred_file_fragments=("qiongtong-baojian/", "ditian-sui/tong-shen-lun_29_han-nuan"),
            day_gan=_day_gan(chart),
            month_zhi=_month_zhi(chart),
            season=_season(chart),
            strict_chart_axis=True,
            selector_hint="调候问题优先选《穷通宝鉴》中日干×月令对应段；其次才选寒暖燥湿通论。",
            term_boosts=("专用", "先取", "次用", "寒", "暖", "燥", "湿"),
        )

    if dispatch_kind == "relationship":
        # 男命:财=妻 → 论财 / 何知章 / 渊海正偏财 这些"财章"也是"妻论"。
        # 女命:官杀=夫 + 滴天髓女命章 是核心(老 policy 漏了)。
        gender = _gender(chart)
        base_allowed = [
            "ditian-sui/liu-qin-lun_01_fu-qi",
            "yuanhai-ziping/10_liu-qin-lun",
            "yuanhai-ziping/11_nv-ming-lun",
        ]
        base_preferred = ["ditian-sui/liu-qin-lun_01_fu-qi.md"]
        base_term_boosts = ("夫妻", "妻", "夫", "婚", "配偶", "财以妻")
        positive_domains: tuple[str, ...] = ("六亲",)
        if gender == "male":
            base_allowed.extend([
                "ziping-zhenquan/33_lun-cai",
                "ziping-zhenquan/34_lun-cai-qu-yun",
                "ditian-sui/liu-qin-lun_05_he-zhi-zhang",
                "yuanhai-ziping/06_shi-shen_zheng-cai-pian-cai",
            ])
            base_preferred.extend([
                "ditian-sui/liu-qin-lun_05_he-zhi-zhang.md",
                "ziping-zhenquan/33_lun-cai.md",
            ])
            base_term_boosts = base_term_boosts + ("财气", "财星", "妻财", "正财", "偏财")
            selector_hint = (
                "男命婚姻/正缘:财即妻;优先选夫妻章、论财、何知章、渊海正偏财;"
                "子女章除非同时直接谈夫妻,否则不要选。"
            )
        elif gender == "female":
            base_allowed.append("ditian-sui/liu-qin-lun_06_nv-ming-zhang")
            base_preferred.append("ditian-sui/liu-qin-lun_06_nv-ming-zhang.md")
            positive_domains = ("六亲", "女命")
            base_term_boosts = base_term_boosts + ("夫星", "官星", "夫子两宫", "女命")
            selector_hint = (
                "女命婚姻/正缘:官杀即夫;优先选滴天髓女命章、渊海女命论、夫妻章;"
                "子女章除非同时直接谈夫妻,否则不要选。"
            )
        else:
            selector_hint = (
                "婚姻/正缘问题优先选夫妻、夫星、妻星;"
                "性别未知时同时容纳财章(男命妻论)与女命章。"
            )
            # gender 未知 — 把男命财章和女命章都放进 allowed,容错保
            base_allowed.extend([
                "ziping-zhenquan/33_lun-cai",
                "ditian-sui/liu-qin-lun_05_he-zhi-zhang",
                "ditian-sui/liu-qin-lun_06_nv-ming-zhang",
            ])

        return RetrievalPolicy(
            kind=kind,
            positive_domains=positive_domains,
            allowed_file_fragments=tuple(base_allowed),
            preferred_files=tuple(base_preferred),
            preferred_file_fragments=("fu-qi", "夫妻"),
            rejected_file_fragments=("zi-nv",),
            selector_hint=selector_hint,
            term_boosts=base_term_boosts,
        )

    if dispatch_kind == "persona":
        # 真实语料里 domain=性情 的 claim 只有 ~25 条,分布在 xing-qing 8 +
        # 渊海04干支体象 9 + 滴天髓何知章 8 等。原 policy 让 xing-qing 整章
        # 30+ claim 都通过 allowed,导致 xing-qing 的 22+ 非性情 claim 也被
        # 召回,把候选池吃光,渊海04干支体象和 三命通会论X日 都进不来。
        # 修正:用 required_domains=性情/外貌 强约束,只让真正标了相关
        # domain 的 claim 通过;同时加 渊海04干支体象 (它在 personality
        # policy 里是 preferred,persona 也该有);加 day_gan-specific term
        # 让 三命通会"论X日生人"通过 BM25 浮上来。
        day_gan = _day_gan(chart)
        return RetrievalPolicy(
            kind=kind,
            positive_domains=("性情", "六亲论·性情", "外貌"),
            allowed_file_fragments=(
                "ditian-sui/liu-qin-lun_24_xing-qing",
                "ziping-zhenquan/04_lun-shi-gan-pei-he-xing-qing",
                "yuanhai-ziping/03_lun-ji-bing-xing-qing",
                "yuanhai-ziping/04_gan-zhi-ti-xiang",
                # 三命通会"论X日生人"分散在 juan-04 / juan-05;但 juan-05 偏
                # 调候,需要 required_domains 把非性情段过滤掉。
                "sanming-tonghui/juan-04",
                "sanming-tonghui/juan-05",
            ),
            preferred_files=(
                "ditian-sui/liu-qin-lun_24_xing-qing.md",
                "ziping-zhenquan/04_lun-shi-gan-pei-he-xing-qing.md",
                "yuanhai-ziping/04_gan-zhi-ti-xiang.md",
            ),
            # 强约束: 必须有 性情 / 外貌 / 相关 domain, 或者文本含性情关键词
            required_domains=("性情", "外貌", "六亲论·性情"),
            required_terms=(
                "性情", "为人", "刚柔",
                f"论{day_gan}日生人" if day_gan else "",
                f"{day_gan}日生" if day_gan else "",
                "天干体象", "地支体象",
            ),
            day_gan=day_gan,
            month_zhi=_month_zhi(chart),
            strict_chart_axis=False,
            selector_hint=(
                "古书定调·画像 — 优先选 4 个层次:1) 滴天髓性情章直断 "
                "(如'五气不戾,性情中和');2) 三命通会论X日生人通用判文 "
                "(按日干);3) 渊海子平干支体象 (天干体象/地支体象);"
                "4) 子平真诠十干配合论性情。不要选疾病、行运、富贵贫贱、"
                "调候用神等其它维度;同一文件最多 2 条,跨来源铺开。"
            ),
            term_boosts=tuple(t for t in (
                "性情", "为人", "刚柔", "中和", "偏枯",
                "天干体象", "地支体象",
                f"论{day_gan}日生人" if day_gan else "",
                f"{day_gan}日生" if day_gan else "",
            ) if t),
        )

    if dispatch_kind == "verdict":
        verdict_hint = (
            "古书定调·定语 — 选 ≤50 字的格局成败 / 用神成救短判语；"
            "含'贫夭刑伤克妻'极端凶词时只在与制化办法同段才选。"
        )
        verdict_allowed = [
            "ziping-zhenquan/09_lun-yong-shen-cheng-bai-jiu-ying",
            "ziping-zhenquan/10_lun-yong-shen-bian-hua",
            "ziping-zhenquan/12_lun-yong-shen-ge-ju-gao-di",
            "ziping-zhenquan/13_lun-yong-shen-yin-cheng-de-bai-yin-bai-de-cheng",
            "yuanhai-ziping/12_fu-lun_zi-ping-ju-yao-xi-ji-ji-shan",
            # 三命通会论命格高低 / 论富贵贫贱在 juan-06 / juan-12 但
            # juan-12 含太多极端凶词，由 polisher 阶段再过滤
            "sanming-tonghui/juan-06",
        ]
        verdict_preferred = [
            "ziping-zhenquan/12_lun-yong-shen-ge-ju-gao-di.md",
            "ziping-zhenquan/13_lun-yong-shen-yin-cheng-de-bai-yin-bai-de-cheng.md",
        ]
        if _yongshen_school_diverged(chart):
            day_gan = _day_gan(chart)
            qiongtong_file = _QIONGTONG_BY_DAY_GAN.get(day_gan, "")
            if qiongtong_file:
                verdict_allowed.append(qiongtong_file)
                verdict_preferred.append(f"{qiongtong_file}.md")
            verdict_hint += (
                " 注意:本盘调候用神与格局用神分歧 — 各保留一条"
                "调候派(穷通宝鉴)与格局派(子平真诠)证据,便于呈现两派对照。"
            )
        return RetrievalPolicy(
            kind=kind,
            positive_domains=("格局成败", "用神取舍"),
            allowed_file_fragments=tuple(verdict_allowed),
            preferred_files=tuple(verdict_preferred),
            selector_hint=verdict_hint,
            term_boosts=("成", "败", "用神", "格局", "高", "贵", "清"),
        )

    if dispatch_kind == "wealth":
        return RetrievalPolicy(
            kind=kind,
            positive_domains=("财官",),
            allowed_file_fragments=(
                "ditian-sui/liu-qin-lun_05_he-zhi-zhang",
                "yuanhai-ziping/06_shi-shen_zheng-cai-pian-cai",
                "ziping-zhenquan/33_lun-cai",
                "ziping-zhenquan/34_lun-cai-qu-yun",
                # 财运总论仍以前四种为主；三命通会这里仅放行
                # combo.day_hour / 时上偏财 这类字面命中的具体旁证。
                "sanming-tonghui/juan-05",
                "sanming-tonghui/juan-08",
                "sanming-tonghui/juan-09",
            ),
            preferred_files=(
                "ditian-sui/liu-qin-lun_05_he-zhi-zhang.md",
                "yuanhai-ziping/06_shi-shen_zheng-cai-pian-cai.md",
                "ziping-zhenquan/33_lun-cai.md",
                "ziping-zhenquan/34_lun-cai-qu-yun.md",
            ),
            rejected_file_fragments=("sanming-tonghui/juan-12",),
            selector_hint="财运问题优先选财星、财格、财气通门户和正偏财章节；泛口诀、泛气候靠后。",
            term_boosts=("财气", "财星", "财格", "正财", "偏财", "食伤生财"),
        )

    if dispatch_kind == "meta":
        # 主十神泛化:七杀/正官/正财/偏财/正印/偏印/食神/伤官 都按查表路由。
        # 早先只有七杀被特殊处理,导致正官/财格/伤官等命盘的 meta 检索退回到
        # 默认空 policy,失去了 ziping-zhenquan/31_lun-zheng-guan 等核心章节
        # 的优先权——这是单点修复未泛化的工程债。
        meta_policy = _meta_policy_for_main_shishen(
            chart, kind, _main_shishen(chart),
        )
        if meta_policy is not None:
            return meta_policy

    if dispatch_kind == "liunian":
        return RetrievalPolicy(
            kind=kind,
            positive_domains=("行运",),
            allowed_file_fragments=(
                "ziping-zhenquan/25_lun-xing-yun",
                "ziping-zhenquan/26_lun-xing-yun-cheng-ge-bian-ge",
                "ditian-sui/liu-qin-lun_28_sui-yun",
                "yuanhai-ziping/02_lun-ri-zhu-yue-ling-da-yun-tai-sui",
            ),
            required_domains=("行运",),
            required_terms=("行运", "岁运", "太岁", "流年", "大运"),
            preferred_files=(
                "ziping-zhenquan/25_lun-xing-yun.md",
                "ziping-zhenquan/26_lun-xing-yun-cheng-ge-bian-ge.md",
                "ditian-sui/liu-qin-lun_28_sui-yun.md",
            ),
            selector_hint="大运/流年问题优先选行运、岁运、成格变格章节；不要只选原局格局通论。",
            term_boosts=("行运", "岁运", "流年", "太岁", "成格", "变格"),
        )

    if dispatch_kind in {"timing", "dayun_step"}:
        return RetrievalPolicy(
            kind=kind,
            positive_domains=("行运",),
            allowed_file_fragments=(
                "xing-yun",
                "sui-yun",
                "da-yun",
                "tai-sui",
                "qu-yun",
            ),
            required_domains=("行运",),
            required_terms=("行运", "岁运", "太岁", "流年", "大运", "取运"),
            preferred_files=(
                "ziping-zhenquan/25_lun-xing-yun.md",
                "ziping-zhenquan/26_lun-xing-yun-cheng-ge-bian-ge.md",
                "ditian-sui/liu-qin-lun_28_sui-yun.md",
            ),
            selector_hint="大运/流年问题优先选行运、岁运、成格变格、取运章节；不要只选原局格局通论。",
            term_boosts=("行运", "岁运", "流年", "太岁", "成格", "变格", "取运"),
        )

    if dispatch_kind == "health":
        # 命理上"病=偏枯/燥湿失衡": 不只看疾病章, 还要看 衰旺/寒暖/燥湿
        # 以及 调候层 (穷通日干月令) 来支撑寒湿燥热致病的判断。
        # 之前单一来源 (滴天髓 ji-bing) 漏掉了渊海"疾病性情"和滴天髓"衰旺"
        # 这两个核心来源——前者是经典疾病论, 后者是命理"病根=偏枯"的依据。
        day_gan = _day_gan(chart)
        qiongtong_file = _QIONGTONG_BY_DAY_GAN.get(day_gan, "")
        return RetrievalPolicy(
            kind=kind,
            positive_domains=("疾病", "用神取舍", "调候"),
            allowed_file_fragments=tuple(f for f in (
                "ditian-sui/liu-qin-lun_25_ji-bing",
                "yuanhai-ziping/03_lun-ji-bing-xing-qing",
                "ditian-sui/tong-shen-lun_17_shuai-wang",
                "ditian-sui/tong-shen-lun_18_zhong-he",
                "ditian-sui/tong-shen-lun_27_gang-rou",
                "ditian-sui/tong-shen-lun_29_han-nuan",
                "ditian-sui/tong-shen-lun_30_zao-shi",
                qiongtong_file,
            ) if f),
            preferred_files=tuple(f for f in (
                "ditian-sui/liu-qin-lun_25_ji-bing.md",
                "yuanhai-ziping/03_lun-ji-bing-xing-qing.md",
                "ditian-sui/tong-shen-lun_17_shuai-wang.md",
                "ditian-sui/tong-shen-lun_29_han-nuan.md",
                f"{qiongtong_file}.md" if qiongtong_file else "",
            ) if f),
            day_gan=day_gan,
            selector_hint=(
                "健康问题以'病=偏枯/寒湿燥热失衡'为本:优先疾病章 + 衰旺/中和章 + "
                "寒暖燥湿;调候层(穷通日干月令)用来支撑寒湿燥热致病的判断;格局富贵段落不要选。"
            ),
            term_boosts=(
                "疾病", "病", "偏枯", "寒", "燥", "湿", "衰旺",
                "中和", "燥热", "寒湿", "亏损",
            ),
        )

    if dispatch_kind == "appearance":
        return RetrievalPolicy(
            kind=kind,
            positive_domains=("外貌", "性情"),
            preferred_files=(
                "sanming-tonghui/juan-07.md",
                "yuanhai-ziping/04_gan-zhi-ti-xiang.md",
            ),
            selector_hint="外貌/气质问题优先选《三命通会》性情相貌、《渊海子平》干支体象、滴天髓性情；不选格局富贵泛论。",
            term_boosts=("性情", "相貌", "形体", "貌", "天干体象", "地支体象"),
        )

    if dispatch_kind == "personality":
        return RetrievalPolicy(
            kind=kind,
            positive_domains=("性情", "外貌"),
            preferred_files=(
                "yuanhai-ziping/04_gan-zhi-ti-xiang.md",
                "ditian-sui/liu-qin-lun_24_xing-qing.md",
                "sanming-tonghui/juan-07.md",
            ),
            selector_hint="性格问题优先选《渊海子平》干支体象（甲X / Y地支段落）、滴天髓性情、《三命通会》性情相貌；不要只选格局通论。",
            term_boosts=("性情", "性格", "刚柔", "天干体象", "地支体象"),
        )

    return RetrievalPolicy(kind=kind)


__all__ = ["RetrievalPolicy", "build_policy"]
