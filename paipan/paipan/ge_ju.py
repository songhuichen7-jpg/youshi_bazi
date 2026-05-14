"""# NOTE: port of archive/paipan-engine/src/ming/geJu.js:1-205.

格局识别 (§2) — Port of paipan-engine/src/ming/geJu.js.

月令三类规则（子平真诠第8、16、45章）：
  - 四仲月（子午卯酉）：专气单一，月令本气透干即成格
  - 四孟月（寅申巳亥）：两藏干，透哪个取哪格；都不透取本气
  - 四库月（辰戌丑未）：须透干方可取格；不透则格局不清

建禄月劫格（第45章）：
  月令本气 = 日主比肩/劫财/禄神 时，改从天干透出的其他十神定格
  （因为"自己不能当用神"）

本模块输出候选格局 + 来源诊断，成败判断和相神分析由 LLM 基于原文做。

Two layers:
  * ``identify_ge_ju(bazi)``  — literal port of Node's ``identifyGeJu`` with
    the same flat input shape and rich dict output (monthZhi, category,
    benQi, benQiShiShen, candidates, mainCandidate, decisionNote, tougans,
    touInMonth).
  * ``compute_ge_ju_and_guards(paipan, day_gan, force)`` — Python-only
    adapter for callers using the nested paipan shape; returns
    ``{geJu, guards}``. ``guards`` is a Python-only concept (Node has no
    such notion in geJu.js); see docstring for the heuristic.
"""
from __future__ import annotations

from typing import Any, Optional, TypedDict

# NOTE: ming/geJu.js:16
from paipan.ganzhi import ZHI_CATEGORY
# NOTE: ming/geJu.js:17
from paipan.cang_gan import get_ben_qi, get_cang_gan_weighted
# NOTE: ming/geJu.js:18
from paipan.shi_shen import get_shi_shen


# NOTE: ming/geJu.js:21-32
# 十神 → 格局名（只列常用；建禄/阳刃特殊处理）
SHI_SHEN_TO_GE: dict[str, str] = {
    "正官": "正官格",
    "七杀": "七杀格",
    "正财": "正财格",
    "偏财": "偏财格",
    "正印": "正印格",
    "偏印": "偏印格",
    "食神": "食神格",
    "伤官": "伤官格",
    "比肩": "建禄格",   # 月令本气为日主比肩 → 建禄
    "劫财": "月刃格",   # 月令本气为日主劫财 → 月刃（又称阳刃格）
}


# NOTE: ming/geJu.js:39-203 — identifyGeJu
def identify_ge_ju(bazi: dict) -> dict:
    """识别格局候选. Port of ``identifyGeJu``.

    Input: ``{yearGan, monthGan, monthZhi, dayGan, hourGan}``.
    Output: rich dict matching Node's return shape.
    """
    # NOTE: ming/geJu.js:40
    year_gan = bazi.get("yearGan")
    month_gan = bazi.get("monthGan")
    month_zhi = bazi.get("monthZhi")
    day_gan = bazi.get("dayGan")
    hour_gan = bazi.get("hourGan")

    # NOTE: ming/geJu.js:41
    ri_zhu = day_gan
    # NOTE: ming/geJu.js:42  四仲/四孟/四库
    category = ZHI_CATEGORY.get(month_zhi)
    # NOTE: ming/geJu.js:43
    ben_qi = get_ben_qi(month_zhi)
    # NOTE: ming/geJu.js:44 — Node's getCangGan returns weighted list; Python equivalent is get_cang_gan_weighted.
    cang_gans = get_cang_gan_weighted(month_zhi) if month_zhi else []

    # NOTE: ming/geJu.js:47 — 透干的非日主天干 (filter Boolean)
    tougans = [g for g in [year_gan, month_gan, hour_gan] if g]

    # NOTE: ming/geJu.js:50 — 找出月支藏干中，哪些透到天干
    tou_in_month = [cg for cg in cang_gans if cg["gan"] in tougans]

    # NOTE: ming/geJu.js:53 — 月令本气对应的十神（日主视角）
    if ben_qi == ri_zhu:
        ben_qi_shi_shen = "比肩"
    else:
        ben_qi_shi_shen = get_shi_shen(ri_zhu, ben_qi) if (ri_zhu and ben_qi) else None

    # NOTE: ming/geJu.js:56-57 — 判断建禄月劫：月令本气是比肩或劫财
    is_jian_lu_or_yang_ren = ben_qi_shi_shen == "比肩" or ben_qi_shi_shen == "劫财"

    candidates: list[dict[str, Any]] = []
    main_candidate: Optional[dict[str, Any]] = None
    decision_note = ""

    if is_jian_lu_or_yang_ren:
        # NOTE: ming/geJu.js:63-88 — 建禄月劫格例外
        ge_name = SHI_SHEN_TO_GE[ben_qi_shi_shen]
        candidates.append({
            "name": ge_name,
            "source": "月令本气",
            "via": ben_qi,
            "note": "自身不能为用，须从其他透干的十神定实际用神",
        })

        # NOTE: ming/geJu.js:73-85 — 找其他透干的"非比劫"十神作为实际用神
        for tg in tougans:
            if tg == ri_zhu:
                continue
            ss = get_shi_shen(ri_zhu, tg)
            if ss == "比肩" or ss == "劫财":
                continue
            name = SHI_SHEN_TO_GE.get(ss, f"{ss}格")
            candidates.append({
                "name": f"{ge_name}+取{ss}为用",
                "source": "天干透出",
                "via": tg,
                "shishen": ss,
            })

        main_candidate = candidates[0]
        decision_note = "建禄月劫格：月令本气为日主比劫，框架名为建禄/月刃，实际取用须看其他透干十神"

    elif category == "四仲":
        # NOTE: ming/geJu.js:90-101 — 四仲月
        name = SHI_SHEN_TO_GE.get(ben_qi_shi_shen, f"{ben_qi_shi_shen}格")
        candidates.append({
            "name": name,
            "source": "月令本气（四仲专气）",
            "via": ben_qi,
            "shishen": ben_qi_shi_shen,
            "isTouGan": ben_qi in tougans,
        })
        main_candidate = candidates[0]
        decision_note = (
            f"四仲月 {month_zhi}，本气 {ben_qi}（{ben_qi_shi_shen}）单一，"
            f"{'已透干' if ben_qi in tougans else '未透干但本气仍成格'}"
        )

    elif category == "四孟":
        # NOTE: ming/geJu.js:103-163 — 四孟月
        primary = [x for x in tou_in_month if x["role"] == "本气" or x["role"] == "中气"]
        yuqi_only = [x for x in tou_in_month if x["role"] == "余气"]
        if len(primary) > 0:
            # NOTE: ming/geJu.js:109 — 本气优先、其次中气
            # JS sort: (a,b) => a.role==='本气' ? -1 : 1 — stable in V8
            primary.sort(key=lambda x: 0 if x["role"] == "本气" else 1)
            for item in primary:
                gan = item["gan"]
                role = item["role"]
                ss = "比肩" if gan == ri_zhu else get_shi_shen(ri_zhu, gan)
                name = SHI_SHEN_TO_GE.get(ss, f"{ss}格")
                candidates.append({
                    "name": name,
                    "source": f"月令{role}透出",
                    "via": gan,
                    "shishen": ss,
                })
            main_candidate = candidates[0]
            decision_note = (
                f"四孟月 {month_zhi}，"
                f"{'/'.join(x['gan'] for x in primary)} 透干（本气优先），"
                f"取{main_candidate['name']}"
            )
            # NOTE: ming/geJu.js:122-131 — 余气透干作为次要候选
            for item in yuqi_only:
                gan = item["gan"]
                role = item["role"]
                ss = "比肩" if gan == ri_zhu else get_shi_shen(ri_zhu, gan)
                candidates.append({
                    "name": f"{SHI_SHEN_TO_GE.get(ss, ss + '格')}（余气透，次要）",
                    "source": "月令余气透出（一般不取）",
                    "via": gan,
                    "shishen": ss,
                })
        elif len(tou_in_month) > 0:
            # NOTE: ming/geJu.js:132-152 — 只有余气透干：优先取本气
            ben_ss = ben_qi_shi_shen
            ben_name = SHI_SHEN_TO_GE.get(ben_ss, f"{ben_ss}格")
            candidates.append({
                "name": ben_name,
                "source": "月令本气（本气中气未透，取本气）",
                "via": ben_qi,
                "shishen": ben_ss,
            })
            for item in yuqi_only:
                gan = item["gan"]
                role = item["role"]
                ss = "比肩" if gan == ri_zhu else get_shi_shen(ri_zhu, gan)
                candidates.append({
                    "name": f"{SHI_SHEN_TO_GE.get(ss, ss + '格')}（余气透，次要）",
                    "source": "月令余气透出",
                    "via": gan,
                    "shishen": ss,
                })
            main_candidate = candidates[0]
            decision_note = (
                f"四孟月 {month_zhi}，只有余气 "
                f"{'/'.join(x['gan'] for x in yuqi_only)} 透干，"
                f"仍以本气 {ben_qi}({ben_ss}) 定格"
            )
        else:
            # NOTE: ming/geJu.js:153-162 — 藏干无一透出
            name = SHI_SHEN_TO_GE.get(ben_qi_shi_shen, f"{ben_qi_shi_shen}格")
            candidates.append({
                "name": name,
                "source": "月令本气（未透干，取本气）",
                "via": ben_qi,
                "shishen": ben_qi_shi_shen,
            })
            main_candidate = candidates[0]
            decision_note = (
                f"四孟月 {month_zhi}，藏干无一透出，"
                f"取本气 {ben_qi}（{ben_qi_shi_shen}）定格"
            )

    elif category == "四库":
        # NOTE: ming/geJu.js:165-189 — 四库月：须透干方可取格
        if len(tou_in_month) > 0:
            for item in tou_in_month:
                gan = item["gan"]
                role = item["role"]
                ss = "比肩" if gan == ri_zhu else get_shi_shen(ri_zhu, gan)
                name = SHI_SHEN_TO_GE.get(ss, f"{ss}格")
                candidates.append({
                    "name": name,
                    "source": f"月令{role}透出（四库必透）",
                    "via": gan,
                    "shishen": ss,
                })
            main_candidate = candidates[0]
            decision_note = (
                f"四库月 {month_zhi}，"
                f"{'/'.join(x['gan'] for x in tou_in_month)} 透干"
            )
        else:
            # NOTE: ming/geJu.js:180-188 — 格局不清
            candidates.append({
                "name": "格局不清",
                "source": "四库月无透干",
                "via": None,
                "note": "需大运流年刑冲开库方能取格",
            })
            main_candidate = candidates[0]
            decision_note = (
                f"四库月 {month_zhi}，藏干均未透干，"
                f"格局暂不清晰，待刑冲开库"
            )

    # NOTE: ming/geJu.js:192-202
    return {
        "monthZhi": month_zhi,
        "category": category,
        "benQi": ben_qi,
        "benQiShiShen": ben_qi_shi_shen,
        "candidates": candidates,
        "mainCandidate": main_candidate,
        "decisionNote": decision_note,
        "tougans": tougans,
        "touInMonth": tou_in_month,
    }


def analyze_geju(bazi: dict, force: dict | None = None) -> dict:
    """Plan 7.1 analyzer API entrypoint.

    ``geJu.js`` does not currently use ``force`` in its decision logic, but the
    parameter is accepted to mirror the requested Python signature.
    """
    _ = force
    return identify_ge_ju(bazi)


class GeJuResult(TypedDict):
    geJu: str
    guards: list[str]


def compute_ge_ju_and_guards(
    paipan: dict,
    day_gan: str,
    force: dict[str, float],
) -> GeJuResult:
    """Given paipan + day gan + force scores, decide geJu and emit guards.

    Python-only adapter. Translates the nested paipan shape
    ``{year:{gan,zhi}, month:{gan,zhi}, ...}`` into Node's flat input,
    calls :func:`identify_ge_ju`, and projects the rich dict down to
    ``{geJu, guards}``.

    * ``geJu`` — ``mainCandidate['name']`` from :func:`identify_ge_ju`,
      or ``'未定'`` if none (defensive — Node always produces a
      mainCandidate when monthZhi is valid).
    * ``guards`` — Python-only concept. Node's ``geJu.js`` has no notion
      of "guards". We derive them as the names of additional candidates
      (``candidates[1:]``) — i.e. structural alternatives that surfaced
      during decision but weren't selected as the main frame. Callers
      that need force-weighted "guards" (e.g. high-force 十神 shielding
      the day master) can compute them separately — this adapter stays
      source-anchored to what Node actually computes.
    """
    # Translate nested paipan → Node-flat bazi shape.
    bazi = {
        "yearGan": paipan.get("year", {}).get("gan"),
        "monthGan": paipan.get("month", {}).get("gan"),
        "monthZhi": paipan.get("month", {}).get("zhi"),
        "dayGan": day_gan,
        "hourGan": paipan.get("hour", {}).get("gan"),
    }
    rich = identify_ge_ju(bazi)

    main = rich.get("mainCandidate")
    ge_ju = main["name"] if main and "name" in main else "未定"

    # guards: names of non-main candidates (Python-only derivation).
    candidates = rich.get("candidates") or []
    guards: list[str] = [c["name"] for c in candidates[1:] if "name" in c]

    return {"geJu": ge_ju, "guards": guards}
