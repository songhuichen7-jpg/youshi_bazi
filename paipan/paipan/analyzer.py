"""# NOTE: port of archive/paipan-engine/src/ming/analyze.js:1-207.

命理层主入口. Literal Python port of the JS analyzer orchestrator, plus the
archive server's placeholder ``suggestYongshen`` heuristic.
"""
from __future__ import annotations

import math

from paipan.cang_gan import get_cang_gan_weighted
from paipan.ge_ju import analyze_geju
from paipan.he_ke import analyze_relations, find_gan_he
from paipan.li_liang import analyze_force
from paipan.shi_shen import get_shi_shen
from paipan.yongshen import build_yongshen


def _js_round(x: float) -> int:
    if x >= 0:
        return math.floor(x + 0.5)
    return -math.floor(-x + 0.5)


def _js_num_str(x: float) -> str:
    if float(x).is_integer():
        return str(int(x))
    return str(x)


def _split_pillar(pillar: str | None) -> dict:
    if not pillar:
        return {"gan": None, "zhi": None}
    return {"gan": pillar[0], "zhi": pillar[1]}


def analyze(paipan_result: dict) -> dict:
    """Analyze a paipan result and return the JS analyzer shape."""
    sizhu = paipan_result.get("sizhu") or {}
    y = _split_pillar(sizhu.get("year"))
    m = _split_pillar(sizhu.get("month"))
    d = _split_pillar(sizhu.get("day"))
    h = _split_pillar(sizhu.get("hour"))

    bazi = {
        "yearGan": y["gan"],
        "yearZhi": y["zhi"],
        "monthGan": m["gan"],
        "monthZhi": m["zhi"],
        "dayGan": d["gan"],
        "dayZhi": d["zhi"],
        "hourGan": h["gan"],
        "hourZhi": h["zhi"],
    }

    ri_zhu = d["gan"]
    hour_unknown = paipan_result.get("hourUnknown") is True

    shi_shen = {
        "year": {"gan": y["gan"], "ss": "比肩" if y["gan"] == ri_zhu else get_shi_shen(ri_zhu, y["gan"])},
        "month": {"gan": m["gan"], "ss": "比肩" if m["gan"] == ri_zhu else get_shi_shen(ri_zhu, m["gan"])},
        "day": {"gan": d["gan"], "ss": "日主"},
        "hour": None if hour_unknown else {
            "gan": h["gan"],
            "ss": "比肩" if h["gan"] == ri_zhu else get_shi_shen(ri_zhu, h["gan"]),
        },
    }

    zhi_detail = {}
    for pos, pillar in (("year", y), ("month", m), ("day", d), ("hour", h)):
        if not pillar["zhi"]:
            continue
        zhi_detail[pos] = {
            "zhi": pillar["zhi"],
            "cangGan": [
                {
                    **cg,
                    "ss": "比肩" if cg["gan"] == ri_zhu else get_shi_shen(ri_zhu, cg["gan"]),
                }
                for cg in get_cang_gan_weighted(pillar["zhi"])
            ],
        }

    force = analyze_force(bazi)
    ge_ju = analyze_geju(bazi, force)

    gan_list = [g for g in [y["gan"], m["gan"], d["gan"], h["gan"]] if g]
    gan_he = find_gan_he(gan_list)
    gan_he_with_ri_zhu = [pair for pair in gan_he if pair["a"] == ri_zhu or pair["b"] == ri_zhu]

    zhi_list = [y["zhi"], m["zhi"], d["zhi"], h["zhi"]]
    zhi_relations = analyze_relations([z for z in zhi_list if z])
    ge_ju_main = (ge_ju or {}).get('mainCandidate', {}).get('name')
    yongshen_dict = build_yongshen(
        rizhu_gan=d["gan"],
        month_zhi=m["zhi"],
        force=force,
        geju=ge_ju_main,
        gan_he=gan_he,
        day_strength=force.get('dayStrength'),
        mingju_zhis=[y["zhi"], m["zhi"], d["zhi"]] + ([h["zhi"]] if h["zhi"] else []),
    )

    return {
        "bazi": bazi,
        "shiShen": shi_shen,
        "zhiDetail": zhi_detail,
        "force": {
            "dayStrength": force["dayStrength"],
            "sameSideScore": force["sameSideScore"],
            "otherSideScore": force["otherSideScore"],
            "sameRatio": force["sameRatio"],
            "congCandidate": force["congCandidate"],
            "scores": force["scoresNormalized"],
            "pairs": force["pairs"],
            "relations": force["relations"],
            "contributions": force["contributions"],
        },
        "geJu": ge_ju,
        "ganHe": {
            "all": gan_he,
            "withRiZhu": gan_he_with_ri_zhu,
        },
        "zhiRelations": zhi_relations,
        "notes": _build_notes(force, ge_ju, zhi_relations),
        "yongshen": yongshen_dict["primary"],
        "yongshenDetail": yongshen_dict,
    }


def _build_notes(force: dict, ge_ju: dict, zhi_relations: dict) -> list[dict]:
    notes: list[dict] = []

    for group, members in force["pairs"].items():
        p1, p2 = members
        if abs(p1["score"] - p2["score"]) > 3:
            dominant = p1["name"] if p1["score"] > p2["score"] else p2["name"]
            notes.append({
                "type": "pair_mismatch",
                "group": group,
                "dominant": dominant,
                "message": (
                    f'{group} 组中 {p1["name"]} ({_js_num_str(p1["score"])}) '
                    f'vs {p2["name"]} ({_js_num_str(p2["score"])}) '
                    f'强度差异大，分析时不能笼统称"{group}旺/弱"'
                ),
            })

    shishang_score = max(force["pairs"]["食伤"][0]["score"], force["pairs"]["食伤"][1]["score"])
    pian_cai_score = next(
        member["score"] for member in force["pairs"]["财"] if member["name"] == "偏财"
    )
    if shishang_score <= 2 and pian_cai_score >= 6:
        notes.append({
            "type": "alt_expression_channel",
            "message": '食伤近零但偏财旺，表达通道换了赛道（感知驱动），不能断"无表达出口"',
        })

    bi_jie_score = max(force["pairs"]["比劫"][0]["score"], force["pairs"]["比劫"][1]["score"])
    if shishang_score <= 2 and bi_jie_score >= 4:
        notes.append({
            "type": "alt_autonomy_channel",
            "message": '食伤近零但比劫有根，仍有"安静的自主决定"，不能断"无叛逆/无自主"',
        })

    for rel in ("偏财", "正财"):
        rels = force["relations"].get(rel) or []
        if any(r["relation"] == "合" for r in rels):
            notes.append({
                "type": "rizhu_he_cai",
                "message": f"日主与{rel}有合，{rel}带有\"情\"的维度，不可简化为功能性占有",
            })

    for rel in ("正官", "七杀"):
        rels = force["relations"].get(rel) or []
        if any(r["relation"] == "合" for r in rels):
            notes.append({
                "type": "rizhu_he_guan",
                "message": f"日主与{rel}有合，关系中有\"主动融合\"意象",
            })

    if zhi_relations["chong"]:
        notes.append({
            "type": "zhi_chong",
            "chongs": zhi_relations["chong"],
            "message": (
                "地支有冲："
                + ", ".join(f'{c["a"]}{c["b"]}' for c in zhi_relations["chong"])
                + "，可能带来突发事件或环境变动"
            ),
        })

    if force["congCandidate"]:
        notes.append({
            "type": "cong_candidate",
            "message": (
                f"日主同类分占比仅 {_js_round(force['sameRatio'] * 100)}%，"
                "疑似从格候选——若成从格，§5 身弱规则完全失效，喜忌逻辑翻转"
            ),
        })

    if ge_ju.get("mainCandidate") and ge_ju["mainCandidate"].get("name") == "格局不清":
        notes.append({
            "type": "geju_unclear",
            "message": "四库月无透干，格局不清，需大运流年刑冲开库后重新定格",
        })

    return notes


def _legacy_suggest_yongshen(analyzer_result: dict) -> str:
    """Plan 7.3: deprecated, kept for any external callers."""
    """Very rough 用神 heuristic from archive/server-mvp/server.js."""
    force = analyzer_result.get("force") or {}
    day_strength = force.get("dayStrength")
    scores = force.get("scores") or {}

    if day_strength in {"身弱", "极弱"}:
        yin = (scores.get("正印") or 0) + (scores.get("偏印") or 0)
        bijie = (scores.get("比肩") or 0) + (scores.get("劫财") or 0)
        return "印（扶身）" if yin >= bijie else "比劫（帮身）"

    if day_strength in {"身强", "极强"}:
        guansha = (scores.get("正官") or 0) + (scores.get("七杀") or 0)
        cai = (scores.get("正财") or 0) + (scores.get("偏财") or 0)
        shishang = (scores.get("食神") or 0) + (scores.get("伤官") or 0)
        top = max(guansha, cai, shishang)
        if top == guansha:
            return "官杀（制身）"
        if top == cai:
            return "财（耗身）"
        return "食伤（泄身）"

    return "中和（无明显偏枯）"
