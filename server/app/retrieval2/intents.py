"""Chart → :class:`QueryIntent` list.

This is the **only file** that knows BaZi chart shape. Retrieval core
consumes ``QueryIntent`` (text + tag constraints + weight + kind) and is
divination-system-agnostic.

What lived in v1 as routing tables is expressed here as structured query
construction — adding a new intent kind is a single ``_emit`` call.
"""
from __future__ import annotations

from typing import Iterable

from .types import QueryIntent

# Chart accessors — tolerant of v1's flat / nested shapes.


def _paipan(chart: dict) -> dict:
    if not isinstance(chart, dict):
        return {}
    return chart.get("PAIPAN") or chart


def _sizhu(chart: dict) -> dict:
    sz = _paipan(chart).get("sizhu") or {}
    return sz if isinstance(sz, dict) else {}


def _day_gan(chart: dict) -> str:
    p = _paipan(chart)
    meta = p.get("META") or {}
    rizhu = str(meta.get("rizhuGan") or p.get("rizhu") or "")
    if rizhu:
        return rizhu[0]
    day_gz = str(_sizhu(p).get("day") or "")
    return day_gz[:1] if day_gz else ""


def _month_zhi(chart: dict) -> str:
    month = str(_sizhu(chart).get("month") or "")
    return month[1:2] if len(month) >= 2 else ""


_SEASON_BY_ZHI = {
    "寅": "春", "卯": "春", "辰": "春",
    "巳": "夏", "午": "夏", "未": "夏",
    "申": "秋", "酉": "秋", "戌": "秋",
    "亥": "冬", "子": "冬", "丑": "冬",
}
_EXTREME_SEASON_ZHI = frozenset("巳午未亥子丑")


def _normalize_shishen(value: str | None) -> str:
    text = str(value or "")
    if not text:
        return ""
    for label in ("七杀", "正官", "偏官", "正财", "偏财", "食神", "伤官",
                  "正印", "偏印", "印绶", "比肩", "劫财", "建禄", "阳刃"):
        if label in text:
            return label
    if "财" in text:
        return "正财"
    if "印" in text:
        return "正印"
    if "煞" in text or "杀" in text:
        return "七杀"
    return ""


def _main_shishen(chart: dict) -> str:
    p = _paipan(chart)
    geju_obj = p.get("geJu") or p.get("ge_ju") or {}
    main = (
        (geju_obj.get("mainCandidate") if isinstance(geju_obj, dict) else None)
        or (geju_obj.get("main_candidate") if isinstance(geju_obj, dict) else None)
        or {}
    )
    if isinstance(main, dict):
        cand = _normalize_shishen(main.get("shishen") or main.get("name"))
        if cand:
            return cand
    return _normalize_shishen(p.get("geju"))


def _yongshen_candidates(chart: dict) -> list[dict]:
    detail = _paipan(chart).get("yongshenDetail") or {}
    if not isinstance(detail, dict):
        return []
    return [c for c in (detail.get("candidates") or []) if isinstance(c, dict)]


def _day_strength_label(chart: dict) -> str:
    raw = str(_paipan(chart).get("dayStrength") or "")
    if "极弱" in raw or "极衰" in raw:
        return "极弱"
    if "极强" in raw or "极旺" in raw:
        return "极强"
    if "弱" in raw or "衰" in raw or "轻" in raw:
        return "身弱"
    if "强" in raw or "旺" in raw:
        return "身强"
    if "中和" in raw or "平" in raw:
        return "中和"
    return ""


# 主十神 → 破格条款 (反向检索). 命理上格局成败必须看破格因素,
# 只查正向"七杀格成法"会漏掉"杀重身轻无制"这类关键反向论述。
# Text 同时供 BM25 命中和 selector LLM 理解此 intent 的目的。
_PO_GE_TERMS: dict[str, tuple[str, ...]] = {
    "正官": ("正官格 忌 伤官见官", "刑冲", "官杀混杂", "破官"),
    "七杀": ("七杀格 忌 杀重身轻", "无制", "财生杀过", "杀印混杂"),
    "正财": ("财格 忌 比劫夺财", "财坏印", "财多身弱"),
    "偏财": ("财格 忌 比劫夺财", "财坏印", "时上偏财无依"),
    "正印": ("印格 忌 财坏印", "印重身弱", "印为忌神"),
    "偏印": ("印格 忌 枭神夺食", "财坏印", "偏印重重"),
    "食神": ("食神格 忌 枭神夺食", "食神逢冲", "食重无财"),
    "伤官": ("伤官格 忌 伤官见官", "伤官无财", "伤官无印", "傲物欺人"),
}


# 日支冲合 → 配偶宫 / 性格信号关键词. 命理上日支为夫妻宫,
# 被冲被合常被解为关系动荡/暗合/婚情转折等;只看格局会漏这一根轴。
_DAY_BRANCH_HINT: dict[str, str] = {
    "chong":  "日支被冲 配偶宫不稳 婚情动荡",
    "liuHe":  "日支六合 暗合 婚情牵连",
    "sanHe":  "日支三合 局气牵动 关系扩散",
    "banHe":  "日支半合 暗动 关系微妙",
    "sanHui": "日支三会 方局气重 配偶宫并入大势",
}


# 流派分歧检测词 (匹配 yongshenDetail.warnings 里的字样).
# 八字 engine 在 调候 != 格局 用神时显式产 warning("古籍两派各有取法"),
# 我们识别这种 warning 后,主动发两路 intent 让 selector 各取一条对照。
_SCHOOL_DIVERGENCE_PATTERNS = ("两派", "流派", "古籍两", "调候 != 格局")


_DOMAIN_TABLE: dict[str, tuple[dict[str, tuple[str, ...]], str]] = {
    "meta":         ({"domain": ("用神取舍", "格局成败")}, "用神 格局 月令"),
    "career":       ({"domain": ("财官", "格局成败")}, "事业 财官 格局"),
    "wealth":       ({"domain": ("财官",)}, "财 偏财 正财"),
    "personality":  ({"domain": ("性情", "外貌")}, "性情 性格 五行刚柔"),
    "relationship": ({"domain": ("六亲",)}, "夫妻 婚姻 妻财 配偶"),
    "appearance":   ({"domain": ("外貌", "性情")}, "性情相貌 形体"),
    "health":       ({"domain": ("疾病",)}, "疾病 衰旺"),
    "timing":       ({"domain": ("行运",)}, "大运 流年 岁运"),
    "dayun_step":   ({"domain": ("行运", "用神取舍")}, "大运 用神"),
    "liunian":      ({"domain": ("行运",)}, "流年 岁运 太岁 行运"),
    "special_geju": ({"domain": ("格局成败",)}, "特殊格局 外格"),
    # 用户问"用一首歌/电影/书形容这盘"——本质是性情+表达层面的比喻，
    # 走 personality 同款 domain，让 LLM 既有性情材料又能援引五行刚柔
    "media":        ({"domain": ("性情", "外貌")}, "性情 性格 比喻 形容"),
    # 古书定调 — 双 pool retrieval
    "persona":      ({"domain": ("性情", "六亲论·性情")}, "性情 命例 X日元 生于 X月"),
    "verdict":      ({"domain": ("格局成败", "用神取舍")}, "格局成败 用神成救 高下"),
    "other":        ({"domain": ("用神取舍",)}, ""),
}


def _emit(
    out: list[QueryIntent],
    *,
    text: str = "",
    constraints: dict[str, Iterable[str]] | None = None,
    weight: float = 1.0,
    kind: str = "generic",
) -> None:
    cleaned: dict[str, tuple[str, ...]] = {}
    for k, vs in (constraints or {}).items():
        tup = tuple(v for v in (vs or ()) if v)
        if tup:
            cleaned[k] = tup
    if not text and not cleaned:
        return
    out.append(QueryIntent(text=text, constraints=cleaned, weight=weight, kind=kind))


def bazi_chart_to_intents(
    chart: dict,
    kind: str = "meta",
    user_message: str | None = None,
) -> list[QueryIntent]:
    """Build the search intent list for a BaZi chart + intent kind."""
    p = _paipan(chart)
    out: list[QueryIntent] = []

    if kind == "chitchat":
        return out

    day_gan = _day_gan(p)
    month_zhi = _month_zhi(p)
    season = _SEASON_BY_ZHI.get(month_zhi, "")
    strength = _day_strength_label(p)
    main = _main_shishen(p)

    # 1. 调候 — 日干 × 月支 — always cheap & high-hit
    if day_gan or month_zhi:
        _emit(out,
            text=f"{day_gan or ''}日 {month_zhi or ''}月 调候 寒暖燥湿".strip(),
            constraints={
                "day_gan": (day_gan,) if day_gan else (),
                "month_zhi": (month_zhi,) if month_zhi else (),
                "yongshen_method": ("调候",),
            },
            weight=1.0, kind="tiaohou",
        )

    # 2. Main 格局
    if main:
        cons: dict[str, Iterable[str]] = {"shishen": (main,)}
        if strength:
            cons["day_strength"] = (strength,)
        _emit(out, text=f"{main} {strength}".strip(),
              constraints=cons, weight=1.0, kind="main_geju")

    # 3. 用神 candidates
    seen: set[str] = set()
    for cand in _yongshen_candidates(p):
        method = str(cand.get("method") or "").strip().split()[0] if cand.get("method") else ""
        name = str(cand.get("name") or "").strip()
        source = str(cand.get("source") or "").strip()
        if not method and not name:
            continue
        if method in seen:
            continue
        seen.add(method)
        cand_shishen = _normalize_shishen(name)
        cons = {}
        if method:
            cons["yongshen_method"] = (method,)
        if cand_shishen:
            cons["shishen"] = (cand_shishen,)
        text = " ".join(t for t in (method, name, source) if t)
        _emit(out, text=text, constraints=cons, weight=0.85,
              kind=f"yongshen.{method or 'unknown'}")

    # 4. Domain anchor for the intent kind
    dom_cons, dom_text = _DOMAIN_TABLE.get(kind, ({}, ""))
    if dom_cons or dom_text:
        _emit(out, text=dom_text, constraints=dom_cons, weight=0.7,
              kind=f"domain.{kind}")

    # 5. Extreme-season climate hint
    if month_zhi in _EXTREME_SEASON_ZHI:
        _emit(out, text="寒暖 调候 偏枯",
              constraints={"season": (season,) if season else (),
                           "yongshen_method": ("调候",)},
              weight=0.5, kind="climate.extreme")

    # 6. 七杀 + 身弱 — special combo
    if main == "七杀" and strength in {"身弱", "极弱"}:
        _emit(out, text="杀重身轻 用印 制煞 化煞",
              constraints={
                  "shishen": ("七杀", "正印", "偏印"),
                  "yongshen_method": ("通关", "扶抑"),
                  "day_strength": ("身弱", "极弱"),
              },
              weight=0.8, kind="combo.shaqing_yinzhong")

    # 7. User question — pure text
    if user_message:
        _emit(out, text=user_message[:200], weight=0.75, kind="user_msg")

    # 8. Day-Hour pillar combo — BM25-only intent that unlocks the
    # 三命通会 卷八/卷九 "六X日Y時斷" catalogs. These chapters are
    # organised by day-stem + hour-pillar pairs (e.g. "甲日戊辰時 天財坐庫
    # 時上偏財遇龍守庫…") — useful for chat questions about wealth /
    # career / relationships where the time pillar gives concrete advice,
    # but too narrow for the meta overview panel (which wants 调候 / 格局
    # / 用神 总论 instead). Skip this in meta kind.
    day_pillar = str(_sizhu(p).get("day") or "")
    hour_pillar = str(_sizhu(p).get("hour") or "")
    if kind not in {"meta", "chitchat"} and day_gan and len(hour_pillar) >= 2:
        hour_gan = hour_pillar[0]
        hour_shishen = ""
        try:
            from paipan.shi_shen import get_shi_shen
            hour_shishen = get_shi_shen(day_gan, hour_gan) or ""
        except Exception:  # noqa: BLE001
            pass
        text_parts = []
        if len(day_pillar) >= 2:
            text_parts.append(f"{day_pillar}日{hour_pillar}時")
        text_parts.append(f"{day_gan}日{hour_pillar}時")
        if hour_shishen:
            text_parts.append(f"时上{hour_shishen}")
        text = " ".join(dict.fromkeys(text_parts))
        _emit(out, text=text, weight=0.65, kind="combo.day_hour")

    # 9. 六亲专篇 — keyword-triggered. Generic relationship intent finds
    # marriage/财官 essays but misses the targeted "论父 / 论母 / 论妻妾 /
    # 论子息" chapters in 渊海子平·卷十. Without these, "我父亲怎么样"
    # returns marriage essays instead.
    if user_message:
        liu_qin_keywords: list[tuple[tuple[str, ...], str]] = [
            (("父亲", "父"), "论父 父亲 印为父"),
            (("母亲", "母", "妈"), "论母 母亲 食伤为母"),
            (("兄弟", "姐妹", "哥", "弟", "姐", "妹"), "论兄弟姐妹 比劫"),
            (("妻", "老婆", "媳妇", "配偶"), "论妻妾 妻财"),
            (("丈夫", "老公", "夫君"), "论夫 配偶 官星为夫"),
            (("子女", "孩子", "儿子", "女儿", "子息"), "论子息 子女"),
        ]
        for kws, intent_text in liu_qin_keywords:
            if any(kw in user_message for kw in kws):
                _emit(out, text=intent_text, weight=0.7, kind="liu_qin.specific")
                break  # one anchor is enough

    # 10. 神煞专篇 — keyword-triggered. Tokenizer normalises 繁→简 in
    # both index and query, so a single 简体 form per term suffices and
    # matches whether the user types 华盖 or 華蓋 and the corpus stores
    # 華蓋 or 华盖.
    if user_message:
        shen_sha_terms = [
            "桃花", "华盖", "天乙", "羊刃", "阳刃", "魁罡",
            "月德", "天德", "禄神", "驿马", "孤辰", "寡宿",
            "金舆", "三奇", "贵人",
        ]
        # Normalise the user message once so we hit either form in the input.
        from .normalize import normalize as _norm  # local import to avoid cycle
        normalised_msg = _norm(user_message)
        seen: set[str] = set()
        for term in shen_sha_terms:
            if _norm(term) in normalised_msg and term not in seen:
                _emit(out, text=f"{term} 神煞", weight=0.7,
                      kind=f"shen_sha.{term}")
                seen.add(term)
        if any(kw in normalised_msg for kw in ("神煞", "凶煞", "吉神")) and not seen:
            _emit(out, text="神煞 吉神凶煞", weight=0.6,
                  kind="shen_sha.overview")

    # 11. 干支体象 — for personality questions. 渊海子平 04 卷 "天干体象 /
    # 地支体象" is the canonical reference for "this person looks/acts like…"
    # but the existing personality intent only routes via domain=性情.
    _GAN_WUXING = {"甲":"木","乙":"木","丙":"火","丁":"火","戊":"土",
                    "己":"土","庚":"金","辛":"金","壬":"水","癸":"水"}
    if kind in {"personality", "appearance"} and day_gan:
        wuxing = _GAN_WUXING.get(day_gan, "")
        text = f"{day_gan}{wuxing}天干体象 性情相貌".strip()
        _emit(out, text=text, weight=0.7, kind="combo.gan_xiang")

    # 12. 女命专论 — when 命主 is female, 渊海子平·11 全卷 are gender-
    # specific (女命赋, 女命富贵贫贱篇, 女命贵格/贱格). Otherwise women
    # users get male-frame readings.
    gender = str((p.get("gender") or "")).lower()
    if gender in {"female", "女", "f"} and kind in {"meta", "relationship", "career", "wealth", "personality"}:
        _emit(out, text="女命 阴命 妇人总诀 女命赋", weight=0.7, kind="combo.nv_ming")

    # 13. 当前流年 / 当前大运 — when the user asks "今年/最近/这两年" or
    # the intent is timing-flavoured, auto-anchor to the current 流年
    # ganzhi and current 大运 ganzhi. paipan ships these as todayYearGz
    # and xingyun.dayun[*].isCurrent. Without this, "今年怎么样" only
    # gets generic 行运 chapters and never the specific 太岁/大运
    # combination that's actually live.
    today_year_gz = str(p.get("todayYearGz") or "")
    current_dayun_gz = ""
    xingyun = p.get("xingyun") or {}
    for du in (xingyun.get("dayun") or []):
        if isinstance(du, dict) and du.get("isCurrent"):
            current_dayun_gz = str(du.get("ganzhi") or "")
            break
    asks_recent = bool(user_message) and any(
        kw in (user_message or "")
        for kw in ("今年", "明年", "最近", "近两年", "近几年", "这两年", "今岁", "近期")
    )
    if (asks_recent or kind in {"timing", "liunian", "dayun_step"}) and today_year_gz:
        text = f"{today_year_gz}流年 太岁"
        if current_dayun_gz:
            text += f" {current_dayun_gz}大运"
        _emit(out, text=text, weight=0.7, kind="combo.current_yun")

    # 14. 破格条款反向检索 — 主十神成法之外,还要检索"忌见 X"这类
    # 反向论述。命理上格局成败 = 正向成法 + 反向破格,缺一不可。
    if main and kind in {"meta", "verdict", "career", "wealth"}:
        po_ge = _PO_GE_TERMS.get(main)
        if po_ge:
            _emit(out, text=" ".join(po_ge), weight=0.6, kind="combo.po_ge")

    # 15. 日支冲合 — 关系/性情分析的关键命理信号. 日支为夫妻宫:
    # 被冲是关系动荡的传统象义,被合常被解为暗合/牵连。
    # 在性格 / 关系 / meta intent 下都该检索,但权重 0.55 别压过主轴。
    zhi_relations = p.get("zhiRelations") or {}
    if (
        isinstance(zhi_relations, dict)
        and kind in {"meta", "relationship", "personality", "appearance"}
    ):
        DAY_IDX = 2
        for rel_kind in ("chong", "liuHe", "sanHe", "banHe", "sanHui"):
            entries = zhi_relations.get(rel_kind) or []
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                # 三合/三会用 zhi 列表 (无 idx_a/idx_b),其它用 idx
                involves_day = (
                    entry.get("idx_a") == DAY_IDX
                    or entry.get("idx_b") == DAY_IDX
                    or (
                        rel_kind in {"sanHe", "banHe", "sanHui"}
                        and len(_sizhu(p).get("day", "")) >= 2
                        and _sizhu(p)["day"][1] in (entry.get("zhi") or ())
                    )
                )
                if involves_day:
                    hint = _DAY_BRANCH_HINT.get(rel_kind, "")
                    if hint:
                        _emit(out, text=hint, weight=0.55,
                              kind="combo.day_branch_relation")
                    break  # 一种关系类型只发一条,避免重复

    # 16. 流派分歧 — 八字 engine 在 调候 != 格局 用神时产 warning,
    # 我们识别后主动发两路 intent (school.tiaohou + school.geju),
    # 让 selector 各取一条对照,LLM 输出能呈现"按 A 派 X / 按 B 派 Y"。
    detail = p.get("yongshenDetail") or {}
    if isinstance(detail, dict):
        warnings = detail.get("warnings") or []
        if not isinstance(warnings, list):
            warnings = [warnings]
        diverged = any(
            isinstance(w, str) and any(pat in w for pat in _SCHOOL_DIVERGENCE_PATTERNS)
            for w in warnings
        )
        if diverged and kind in {"meta", "verdict"}:
            tiaohou_text = (
                f"{day_gan or ''}日 {month_zhi or ''}月 调候 寒暖燥湿 穷通"
            ).strip()
            _emit(out, text=tiaohou_text, weight=0.85,
                  constraints={"yongshen_method": ("调候",),
                               "day_gan": (day_gan,) if day_gan else (),
                               "month_zhi": (month_zhi,) if month_zhi else ()},
                  kind="school.tiaohou")
            geju_text = f"{main or ''}格 用神 成败 救应 子平真诠".strip()
            _emit(out, text=geju_text, weight=0.85,
                  constraints={"yongshen_method": ("格局",),
                               "shishen": (main,) if main else ()},
                  kind="school.geju")

    return out


__all__ = ["bazi_chart_to_intents"]
