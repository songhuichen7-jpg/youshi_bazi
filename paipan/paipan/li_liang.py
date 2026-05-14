"""# NOTE: port of archive/paipan-engine/src/ming/liLiang.js:1-203.

力量擂台 (§4). Literal Python port of the JS analyzer force engine.

Evaluates each 十神 across 4 dimensions: 透干、得令、根、合克.

Node exports ported:
    WEIGHTS
    analyzeForce → analyze_force

Python-only additions:
    compute_force — thin adapter used by the Python spec test suite that
    translates ``{year, month, day, hour}`` nested input to Node's flat
    ``{yearGan, yearZhi, ...}`` shape and returns just the raw ten-gods
    scores dict. No Node counterpart — documented as adapter-only.

Bug/quirk notes (preserved verbatim from Node):
    - ``keDiscount`` is defined in ``WEIGHTS`` but never applied anywhere in
      the algorithm. Port keeps it as a dead constant.
    - He-reduction formula is intentionally
      ``reduction = scores[ss] * (1 - heDiscount); scores[ss] -= reduction``
      rather than ``scores[ss] *= heDiscount``. The ``adjustments[].reduction``
      value is oracle-fixed to 0.1 precision, so the formula is ported
      literally.
"""
from __future__ import annotations

import math

from paipan.cang_gan import get_ben_qi, get_cang_gan_weighted
from paipan.ganzhi import GAN_WUXING, WUXING_KE, WUXING_SHENG
from paipan.he_ke import find_gan_he, is_gan_he
from paipan.shi_shen import SHI_SHEN_PAIRS, get_shi_shen

# Plan 7.6 §4.3 — 5-bin day_strength thresholds (keyed on same_ratio ∈ [0, 1]).
# Existing Plan 7.3 boundaries (0.55 / 0.35 / 0.15) are now named.
# 极强 / 极弱 boundaries come from Task 0 sampling
# (seed=42, N=1000, paipan/scripts/sample_day_strength.py).
THRESHOLD_JI_QIANG = 0.76
THRESHOLD_SHEN_QIANG = 0.55
THRESHOLD_ZHONG_HE = 0.35
THRESHOLD_JI_RUO = 0.12
THRESHOLD_CONG_CANDIDATE = 0.15


def _js_round(x: float) -> int:
    """Match JS ``Math.round`` (half-away-from-zero)."""
    if x >= 0:
        return math.floor(x + 0.5)
    return -math.floor(-x + 0.5)


def _classify_day_strength(same_ratio: float) -> str:
    """Classify day strength from the same-side force ratio."""
    if same_ratio >= THRESHOLD_JI_QIANG:
        return "极强"
    if same_ratio >= THRESHOLD_SHEN_QIANG:
        return "身强"
    if same_ratio >= THRESHOLD_ZHONG_HE:
        return "中和"
    if same_ratio >= THRESHOLD_JI_RUO:
        return "身弱"
    return "极弱"


WEIGHTS: dict[str, float] = {
    "tougan": 3.0,
    "deling": 4.0,
    "rootBenQi": 2.0,
    "rootZhongQi": 1.0,
    "rootYuQi": 0.5,
    "heDiscount": 0.4,
    "keDiscount": 0.6,
}

ALL_SHI_SHEN: list[str] = [
    "比肩", "劫财", "食神", "伤官", "正财", "偏财", "正官", "七杀", "正印", "偏印",
]


def _get_rizhu_relation(ri_zhu: str, shi_shen: str, ctx: dict) -> list[dict]:
    """日主与某十神的关系（合/克/生）."""
    gan_list: list[str] = ctx["ganList"]
    results: list[dict] = []

    for i, g in enumerate(gan_list):
        if g == ri_zhu:
            continue
        if get_shi_shen(ri_zhu, g) != shi_shen:
            continue

        gw = GAN_WUXING[g]
        rw = GAN_WUXING[ri_zhu]
        if is_gan_he(ri_zhu, g):
            rel = "合"
        elif WUXING_KE.get(rw) == gw:
            rel = "日主克"
        elif WUXING_KE.get(gw) == rw:
            rel = "克日主"
        elif WUXING_SHENG.get(rw) == gw:
            rel = "日主生"
        elif WUXING_SHENG.get(gw) == rw:
            rel = "生日主"
        elif gw == rw:
            rel = "同类"
        else:
            rel = "无关"

        results.append({"gan": g, "position": i, "relation": rel})
    return results


def analyze_force(bazi: dict) -> dict:
    """计算各十神的力量."""
    year_gan = bazi.get("yearGan")
    year_zhi = bazi.get("yearZhi")
    month_gan = bazi.get("monthGan")
    month_zhi = bazi.get("monthZhi")
    day_gan = bazi.get("dayGan")
    day_zhi = bazi.get("dayZhi")
    hour_gan = bazi.get("hourGan")
    hour_zhi = bazi.get("hourZhi")
    ri_zhu = day_gan

    gans: list[dict] = [x for x in [
        {"gan": year_gan, "pos": "年干"},
        {"gan": month_gan, "pos": "月干"},
        {"gan": day_gan, "pos": "日干"},
        {"gan": hour_gan, "pos": "时干"},
    ] if x["gan"]]

    zhis: list[dict] = [x for x in [
        {"zhi": year_zhi, "pos": "年支"},
        {"zhi": month_zhi, "pos": "月支"},
        {"zhi": day_zhi, "pos": "日支"},
        {"zhi": hour_zhi, "pos": "时支"},
    ] if x["zhi"]]

    scores: dict[str, float] = {}
    contributions: dict[str, dict] = {}
    for s in ALL_SHI_SHEN:
        scores[s] = 0.0
        contributions[s] = {"tougan": [], "deling": None, "roots": [], "adjustments": []}

    for entry in gans:
        if entry["pos"] == "日干":
            continue
        ss = get_shi_shen(ri_zhu, entry["gan"])
        scores[ss] += WEIGHTS["tougan"]
        contributions[ss]["tougan"].append({"gan": entry["gan"], "pos": entry["pos"]})

    month_ben_qi = get_ben_qi(month_zhi) if month_zhi else None
    if month_ben_qi:
        deling_ss = "比肩" if month_ben_qi == ri_zhu else get_shi_shen(ri_zhu, month_ben_qi)
        scores[deling_ss] += WEIGHTS["deling"]
        contributions[deling_ss]["deling"] = {"monthZhi": month_zhi, "benQi": month_ben_qi}

    for zentry in zhis:
        zhi = zentry["zhi"]
        pos = zentry["pos"]
        cg = get_cang_gan_weighted(zhi)
        for cg_entry in cg:
            gan = cg_entry["gan"]
            weight = cg_entry["weight"]
            role = cg_entry["role"]
            ss = "比肩" if gan == ri_zhu else get_shi_shen(ri_zhu, gan)
            if pos == "月支" and role == "本气":
                continue
            if role == "本气":
                w = WEIGHTS["rootBenQi"]
            elif role == "中气":
                w = WEIGHTS["rootZhongQi"]
            else:
                w = WEIGHTS["rootYuQi"]
            scores[ss] += w * weight
            contributions[ss]["roots"].append({
                "zhi": zhi,
                "pos": pos,
                "gan": gan,
                "role": role,
                "weight": w * weight,
            })

    gan_list = [x["gan"] for x in gans]
    he_list = find_gan_he(gan_list)

    for he in he_list:
        for g in (he["a"], he["b"]):
            if g == ri_zhu:
                continue
            ss = get_shi_shen(ri_zhu, g)
            reduction = scores[ss] * (1 - WEIGHTS["heDiscount"])
            scores[ss] -= reduction
            contributions[ss]["adjustments"].append({
                "type": "被合",
                "with": he["b"] if g == he["a"] else he["a"],
                "reduction": _js_round(reduction * 10) / 10,
            })

    max_score = max(max(scores.values()), 1)
    normalized: dict[str, float] = {}
    for s in ALL_SHI_SHEN:
        normalized[s] = _js_round((scores[s] / max_score) * 10 * 10) / 10

    same_side_score = (
        scores["比肩"] + scores["劫财"] + scores["正印"] + scores["偏印"]
    )
    other_side_score = (
        scores["食神"] + scores["伤官"] + scores["正财"] + scores["偏财"]
        + scores["正官"] + scores["七杀"]
    )
    total_score = same_side_score + other_side_score
    same_ratio = same_side_score / total_score if total_score > 0 else 0
    day_strength = _classify_day_strength(same_ratio)

    cong_candidate = same_ratio <= THRESHOLD_CONG_CANDIDATE

    pairs: dict[str, list[dict]] = {}
    for group, members in SHI_SHEN_PAIRS.items():
        pairs[group] = [
            {"name": m, "score": normalized[m], "raw": scores[m]} for m in members
        ]

    relations: dict[str, list[dict]] = {}
    for s in ALL_SHI_SHEN:
        relations[s] = _get_rizhu_relation(
            ri_zhu,
            s,
            {"ganList": gan_list, "zhis": zhis, "heList": he_list},
        )

    return {
        "riZhu": ri_zhu,
        "scoresRaw": scores,
        "scoresNormalized": normalized,
        "contributions": contributions,
        "dayStrength": day_strength,
        "sameSideScore": _js_round(same_side_score * 10) / 10,
        "otherSideScore": _js_round(other_side_score * 10) / 10,
        "sameRatio": _js_round(same_ratio * 100) / 10 / 10,
        "congCandidate": cong_candidate,
        "pairs": pairs,
        "relations": relations,
    }


def compute_force(paipan: dict, day_gan: str) -> dict[str, float]:
    """Python-only adapter used by the spec test suite."""

    def _gan(k: str) -> str | None:
        return paipan.get(k, {}).get("gan")

    def _zhi(k: str) -> str | None:
        return paipan.get(k, {}).get("zhi")

    chart_day_gan = _gan("day")
    if chart_day_gan is not None and chart_day_gan != day_gan:
        raise ValueError(
            f"day_gan mismatch: arg={day_gan!r} vs paipan['day']['gan']={chart_day_gan!r}"
        )

    bazi = {
        "yearGan": _gan("year"),
        "yearZhi": _zhi("year"),
        "monthGan": _gan("month"),
        "monthZhi": _zhi("month"),
        "dayGan": chart_day_gan or day_gan,
        "dayZhi": _zhi("day"),
        "hourGan": _gan("hour"),
        "hourZhi": _zhi("hour"),
    }
    result = analyze_force(bazi)
    return result["scoresRaw"]
