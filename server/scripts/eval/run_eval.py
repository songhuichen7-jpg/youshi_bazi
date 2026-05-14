"""Run retrieval eval against the canonical evidence index.

Phase 3+4: scores top-K retrieval against the deterministic ground truth
built by ``build_canonical_index.py``.

Two modes::

    # Two known regression cases with full pipeline (incl. selector)
    PYTHONPATH=server uv run python -m scripts.eval.run_eval --mode regression

    # All 834 deterministic cases, no selector (top-30 candidate baseline)
    PYTHONPATH=server uv run python -m scripts.eval.run_eval --mode baseline

Output:
* ``server/var/eval/results_<mode>.jsonl`` — per-query scores
* ``server/var/eval/summary_<mode>.json`` — aggregated metrics

The eval is splitter-agnostic: ground truth references canonical_keys, and
chunk → canonical mapping is computed at runtime via normalized substring
match. Re-chunking the corpus does not invalidate the eval set.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Use the main repo's index, not the worktree's (worktree has no var/retrieval2).
REPO_ROOT = Path("/Users/veko/code/usual/bazi-analysis")
os.environ.setdefault(
    "RETRIEVAL2_INDEX_ROOT",
    str(REPO_ROOT / "server" / "var" / "retrieval2"),
)

from app.retrieval2.normalize import normalize  # noqa: E402
from app.retrieval2.service import retrieve_for_chart  # noqa: E402
from app.retrieval3 import (  # noqa: E402
    qtbj_retrieve, smth89_retrieve,
    shensha_retrieve, geju_retrieve, liuqin_retrieve,
    appearance_retrieve, concept_retrieve, theory_retrieve,
    hehua_retrieve,
)

logger = logging.getLogger("eval.run")

CANONICAL_INDEX_PATH = REPO_ROOT / "server" / "var" / "eval" / "canonical_index.json"
OUT_DIR = REPO_ROOT / "server" / "var" / "eval"


# ─────────────────────────────────────────────────────────────────────────────
# Required-phrase extraction for QTBJ canonical sections.
# ─────────────────────────────────────────────────────────────────────────────

# 在 QTBJ 文本里抽取条件分支语：
# - "X透Y藏" / "X藏Y透" / "X两透"
# - "无X" + 后续判语
# - 月份头 ("十二月")
# 这些是分级条文的"原子证据"，phrase_coverage 用它们做 partial credit。
_QTBJ_BRANCH_PATTERNS = [
    re.compile(r"[甲乙丙丁戊己庚辛壬癸]两透"),
    re.compile(r"[甲乙丙丁戊己庚辛壬癸]透[甲乙丙丁戊己庚辛壬癸]藏"),
    re.compile(r"无[甲乙丙丁戊己庚辛壬癸]"),
    re.compile(r"先[甲乙丙丁戊己庚辛壬癸]后[甲乙丙丁戊己庚辛壬癸]"),
    re.compile(r"先用[甲乙丙丁戊己庚辛壬癸]"),
    re.compile(r"次用[甲乙丙丁戊己庚辛壬癸]"),
    re.compile(r"先取[甲乙丙丁戊己庚辛壬癸]"),
]
# 判语 (用作 secondary signal — 出现的判语越多说明覆盖越完整)
_QTBJ_JUDGEMENT_PHRASES = (
    "科甲", "富贵", "贫贱", "寒儒", "异路", "大贵", "小贵",
    "上命", "下格", "平常", "孤贫",
)


def extract_qtbj_required_phrases(canonical_text: str, month_name: str) -> list[str]:
    """从 canonical 文本中抽取关键短语,用于 phrase_coverage 评估。

    返回 8-15 字短句。每句应该是 canonical 内含的连续子串(归一化后)。"""
    text = canonical_text
    norm_text = normalize(text)

    out: list[str] = []
    seen: set[str] = set()

    # 月份头(归一化后)
    head = normalize(month_name)
    if head and head in norm_text:
        out.append(head)
        seen.add(head)

    # 条件分支模式
    for pat in _QTBJ_BRANCH_PATTERNS:
        for m in pat.finditer(text):
            phrase = m.group(0)
            n = normalize(phrase)
            if n and n not in seen:
                out.append(n)
                seen.add(n)

    # 关键判语
    for jp in _QTBJ_JUDGEMENT_PHRASES:
        if jp in text:
            n = normalize(jp)
            if n not in seen:
                out.append(n)
                seen.add(n)

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Eval query shape
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EvalQuery:
    query_id: str
    canonical_key: str
    source_family: str  # "qtbj" / "smth"
    intent_kind: str
    paipan: dict[str, Any]
    user_question: str
    required_phrases: list[str]
    near_miss_keys: list[str] = field(default_factory=list)
    forbidden_pillar_pattern: str | None = None  # for SMTH precision check

    # raw canonical metadata (for diagnostics)
    book: str = ""
    chapter_file: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Build queries from canonical index
# ─────────────────────────────────────────────────────────────────────────────

# 选一个有效的代表性日柱：每个日干配一个固定日支
_REP_DAY_ZHI = {
    "甲": "申", "乙": "酉", "丙": "戌", "丁": "亥", "戊": "子",
    "己": "丑", "庚": "寅", "辛": "卯", "壬": "辰", "癸": "巳",
}
_MONTH_GAN_FOR_REP = "庚"  # 任意月干,只要月支正确即可

_MONTH_ZHI_TO_NAME = {
    "寅": "正月", "卯": "二月", "辰": "三月", "巳": "四月",
    "午": "五月", "未": "六月", "申": "七月", "酉": "八月",
    "戌": "九月", "亥": "十月", "子": "十一月", "丑": "十二月",
}


def _make_paipan(day_pillar: str, month_pillar: str, hour_pillar: str = "甲子") -> dict:
    return {
        "sizhu": {
            "year": "癸未",
            "month": month_pillar,
            "day": day_pillar,
            "hour": hour_pillar,
        },
        "META": {
            "rizhuGan": day_pillar[0],
        },
    }


def build_qtbj_queries(canonical_data: dict) -> list[EvalQuery]:
    out: list[EvalQuery] = []
    for s in canonical_data["qtbj_sections"]:
        day_gan = s["day_gan"]
        month_zhi = s["month_zhi"]
        month_name = s["month_name"]
        day_pillar = day_gan + _REP_DAY_ZHI[day_gan]
        month_pillar = _MONTH_GAN_FOR_REP + month_zhi

        phrases = extract_qtbj_required_phrases(s["text"], month_name)
        if not phrases:
            phrases = [normalize(month_name + day_gan)]

        out.append(EvalQuery(
            query_id=f"QTBJ_{day_gan}_{month_zhi}",
            canonical_key=s["canonical_key"],
            source_family="qtbj",
            intent_kind="meta",
            paipan=_make_paipan(day_pillar, month_pillar),
            user_question=f"{day_gan}日生于{month_name},穷通宝鉴怎么取调候用神?",
            required_phrases=phrases,
            book=s["book"],
            chapter_file=s["chapter_file"],
        ))
    return out


def build_shensha_queries(canonical_data: dict) -> list[EvalQuery]:
    out: list[EvalQuery] = []
    for e in canonical_data.get("shensha_entries", []):
        term = e["term"]
        aliases = e.get("aliases") or []
        # 多 alias 短词作 phrase 候选 — 神煞章节常用 alias 而非全名
        phrase_set: list[str] = []
        for cand in [term, *aliases]:
            n = normalize(cand)
            if n and n not in phrase_set and len(n) <= 6:
                phrase_set.append(n)
        out.append(EvalQuery(
            query_id=f"SHENSHA_{term}",
            canonical_key=e["canonical_key"],
            source_family="shensha",
            intent_kind="meta",
            paipan=_make_paipan("甲申", "庚丑"),
            user_question=f"{term}是什么神煞?",
            required_phrases=phrase_set,
            book=e["book"],
            chapter_file=e["chapter_file"],
        ))
    return out


def build_geju_queries(canonical_data: dict) -> list[EvalQuery]:
    out: list[EvalQuery] = []
    for e in canonical_data.get("geju_entries", []):
        name = e["name"]
        files = e.get("chapter_files") or []
        # 用去掉 "格" 后缀的词作 required phrase — 子平真诠原文常说"正官者..."
        # 而非"正官格者...",带"格"匹配率低反而失真
        bare = name.removesuffix("格").removesuffix("月劫")
        phrase_candidates = [normalize(bare), normalize(name)]
        phrases = [p for p in phrase_candidates if p]
        out.append(EvalQuery(
            query_id=f"GEJU_{name}",
            canonical_key=e["canonical_key"],
            source_family="geju",
            intent_kind="meta",
            paipan=_make_paipan("甲申", "庚丑"),
            user_question=f"什么是{name}?",
            required_phrases=phrases,
            book=e.get("book") or "",
            chapter_file=files[0] if files else "",
        ))
    return out


def build_liuqin_queries(canonical_data: dict) -> list[EvalQuery]:
    out: list[EvalQuery] = []
    question_map = {
        "夫妻": "我老婆怎么样?",
        "子女": "我子息如何?",
        "父": "我父亲怎么样?",
        "母": "我母亲怎么样?",
        "兄弟": "我兄弟姊妹怎么样?",
        "六亲总论": "我的六亲怎么看?",
    }
    for e in canonical_data.get("liuqin_entries", []):
        relation = e["relation"]
        files = e.get("chapter_files") or []
        out.append(EvalQuery(
            query_id=f"LIUQIN_{relation}",
            canonical_key=e["canonical_key"],
            source_family="liuqin",
            intent_kind="relationship",
            paipan=_make_paipan("甲申", "庚丑"),
            user_question=question_map.get(relation, f"我的{relation}怎么样?"),
            required_phrases=[normalize(relation)],
            book=e.get("book") or "",
            chapter_file=files[0] if files else "",
        ))
    return out


def build_appearance_queries(canonical_data: dict) -> list[EvalQuery]:
    out: list[EvalQuery] = []
    for e in canonical_data.get("appearance_entries", []):
        kind = e["kind"]
        aspect = e["aspect"]
        if kind == "gan":
            day_pillar = aspect + "申"
            qid = f"APPEARANCE_GAN_{aspect}"
        elif kind == "zhi":
            day_pillar = "甲" + aspect
            qid = f"APPEARANCE_ZHI_{aspect}"
        else:
            day_pillar = "甲申"
            qid = f"APPEARANCE_{aspect}"

        out.append(EvalQuery(
            query_id=qid,
            canonical_key=e["canonical_key"],
            source_family="appearance",
            intent_kind="appearance",
            paipan=_make_paipan(day_pillar, "庚丑"),
            user_question="我长什么样?",
            required_phrases=[normalize(aspect)] if kind != "general" else [],
            book=e.get("book") or "",
            chapter_file=e.get("chapter_file") or "",
        ))
    return out


def build_theory_queries(canonical_data: dict) -> list[EvalQuery]:
    out: list[EvalQuery] = []
    for e in canonical_data.get("theory_entries", []):
        topic = e["topic"]
        aliases = e.get("aliases") or []
        # phrase 候选: topic + 短 alias
        phrases: list[str] = []
        for cand in [topic, *aliases]:
            n = normalize(cand)
            if n and n not in phrases and len(n) <= 8:
                phrases.append(n)
        out.append(EvalQuery(
            query_id=f"THEORY_{topic}",
            canonical_key=e["canonical_key"],
            source_family="theory",
            intent_kind="meta",
            paipan=_make_paipan("甲申", "庚丑"),
            user_question=f"什么是{topic}?",
            required_phrases=phrases,
            book=e.get("book") or "",
            chapter_file=e.get("chapter_file") or "",
        ))
    return out


def build_concept_queries(canonical_data: dict) -> list[EvalQuery]:
    out: list[EvalQuery] = []
    for e in canonical_data.get("concept_entries", []):
        term = e["term"]
        aliases = e.get("aliases") or []
        files = e.get("chapter_files") or []
        # phrase 候选: term + 短的 aliases (1-3字),覆盖文本里"X者..."这种行文
        phrase_set: list[str] = []
        for cand in [term, *aliases]:
            n = normalize(cand)
            if n and n not in phrase_set and len(n) <= 6:
                phrase_set.append(n)
        out.append(EvalQuery(
            query_id=f"CONCEPT_{term}",
            canonical_key=e["canonical_key"],
            source_family="concept",
            intent_kind="meta",
            paipan=_make_paipan("甲申", "庚丑"),
            user_question=f"什么是{term}?",
            required_phrases=phrase_set,
            book=e.get("book") or "",
            chapter_file=files[0] if files else "",
        ))
    return out


_HEHUA_REF_CHAPTER = "ziping-zhenquan/07_lun-xing-chong-hui-he-xie-fa.md"


def build_hehua_queries(canonical_data: dict | None = None) -> list[EvalQuery]:
    """Hand-curated 合化 detection cases.

    Why not generated from canonical_index: hehua is a structural-fact emitter,
    not a corpus retriever. The canonical_key is synthesized at runtime from
    the chart's earth branches. So we hand-pick representative charts that
    cover each detection mode (三合 / 半三合 / 三会 / 六合, 化神透干 vs 不透干).
    """
    cases = [
        # 1. 三合全 + 化神透干 — veko 真实 case (1973-09-20)
        dict(
            qid="HEHUA_si_you_chou_full_metal_transparent",
            paipan=_make_paipan("己未", "辛酉", "己巳"),  # 年柱 will be 癸丑 below
            year="癸丑",
            ck="hehua::巳酉丑::金",
            phrases=["三合金局", "化神透干", "辛", "食伤"],
        ),
        # 2. 三合全 + 化神不透干
        dict(
            qid="HEHUA_hai_mao_wei_full_wood_opaque",
            paipan=_make_paipan("戊未", "癸卯", "戊辰"),
            year="丁亥",
            ck="hehua::亥卯未::木",
            phrases=["三合木局", "化神木未透干", "官杀"],
        ),
        # 3. 三合全 申子辰
        dict(
            qid="HEHUA_shen_zi_chen_full_water",
            paipan=_make_paipan("甲辰", "壬子", "丙寅"),
            year="壬申",
            ck="hehua::申子辰::水",
            phrases=["三合水局", "化神透干", "壬", "印"],
        ),
        # 4. 半三合 (含中神)
        dict(
            qid="HEHUA_half_si_you_metal",
            paipan=_make_paipan("丙寅", "辛酉", "癸巳"),
            year="甲子",
            ck="hehua::巳酉::金",
            phrases=["半三合金", "化神透干", "辛"],
        ),
        # 5. 三会方局 — 东方木
        dict(
            qid="HEHUA_sanhui_east_wood",
            paipan=_make_paipan("甲辰", "丁卯", "戊申"),
            year="丙寅",
            ck="hehua::寅卯辰::木",
            phrases=["三会木局", "化神透干", "甲"],
        ),
        # 6. 六合 子丑 — element 标 None / 不判化
        dict(
            qid="HEHUA_liuhe_zi_chou",
            paipan=_make_paipan("戊午", "丁丑", "甲寅"),
            year="甲子",
            ck="hehua::子丑::无化",
            phrases=["六合", "子丑", "v1 不判化"],
        ),
    ]
    out: list[EvalQuery] = []
    for c in cases:
        paipan = dict(c["paipan"])
        # Override year pillar (the helper hardcodes 癸未)
        paipan["sizhu"] = {**paipan["sizhu"], "year": c["year"]}
        out.append(EvalQuery(
            query_id=c["qid"],
            canonical_key=c["ck"],
            source_family="hehua",
            intent_kind="meta",
            paipan=paipan,
            user_question="本盘地支有没有合化?",
            required_phrases=[normalize(p) for p in c["phrases"]],
            book="ziping-zhenquan",
            chapter_file=_HEHUA_REF_CHAPTER,
        ))
    return out


def build_smth_queries(canonical_data: dict) -> list[EvalQuery]:
    out: list[EvalQuery] = []
    for e in canonical_data["smth_entries"]:
        day_pillar = e["day_pillar"]
        hour_pillar = e["hour_pillar"]
        day_gan = e["day_gan"]
        # 用 day_gan 配本月支构造命盘 (任意月份均可,SMTH 不依赖月柱)
        month_pillar = _MONTH_GAN_FOR_REP + "丑"

        # required_phrases: 完整日柱+时柱锚 (canonical entry 都包含完整时柱,
        # zhi-only 锚永远不匹配整柱字符串,反而拖低 phrase_coverage 给假信号)
        phrases = [normalize(f"{day_pillar}日{hour_pillar}時")]

        # near_miss: 其他5个同时柱不同日柱的 entry
        near_miss = []
        for d_zhi in ["子", "寅", "辰", "午", "申", "戌"] if day_gan in "甲丙戊庚壬" else ["丑", "卯", "巳", "未", "酉", "亥"]:
            if d_zhi == e["day_zhi"]:
                continue
            other_pillar = day_gan + d_zhi
            near_miss.append(f"smth::{e['volume']}::{other_pillar}::{hour_pillar}")

        out.append(EvalQuery(
            query_id=f"SMTH_{e['volume']}_{day_pillar}_{hour_pillar}",
            canonical_key=e["canonical_key"],
            source_family="smth",
            intent_kind="meta",
            paipan=_make_paipan(day_pillar, month_pillar, hour_pillar),
            user_question=f"{day_pillar}日{hour_pillar}时,三命通会日时诀文怎么说?",
            required_phrases=phrases,
            near_miss_keys=near_miss,
            forbidden_pillar_pattern=day_gan + "X" + "::" + hour_pillar,  # 同干不同支
            book=e["book"],
            chapter_file=e["chapter_file"],
        ))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Chunk → canonical mapping (text containment, normalized)
# ─────────────────────────────────────────────────────────────────────────────

def build_chunk_canonical_map(canonical_data: dict) -> dict[str, list[str]]:
    """Pre-compute chunk_text-anchor → canonical_keys table for fast lookup.

    Returns: anchor_text → list[canonical_key]. At eval time, for each
    retrieved chunk we scan its normalized text for any of these anchors.
    """
    anchor_to_keys: dict[str, list[str]] = defaultdict(list)

    for s in canonical_data["qtbj_sections"]:
        for p in s["paragraphs"]:
            n = normalize(p["text"])
            # 取段首 30 字作为 anchor — 足够区分不同段,又不至于因为后半段差异错配
            anchor = n[:30]
            if len(anchor) >= 12:
                anchor_to_keys[anchor].append(s["canonical_key"])

    for e in canonical_data["smth_entries"]:
        # SMTH anchor: 整条 entry (含日柱时柱前缀) 的归一化文本
        n = normalize(e["text"])
        anchor = n[:40]
        if len(anchor) >= 12:
            anchor_to_keys[anchor].append(e["canonical_key"])
        # 也加一个短锚 — "<day_pillar>日<hour_pillar>時"
        short = normalize(f"{e['day_pillar']}日{e['hour_pillar']}時")
        anchor_to_keys[short].append(e["canonical_key"])

    # 新家族 anchor: 每条 entry 的 text 前 40 字
    for fam_key in ("shensha_entries", "geju_entries", "liuqin_entries",
                    "appearance_entries", "concept_entries", "theory_entries"):
        for e in canonical_data.get(fam_key, []):
            text = e.get("text") or ""
            n = normalize(text)
            anchor = n[:40]
            if len(anchor) >= 12:
                anchor_to_keys[anchor].append(e["canonical_key"])

    return dict(anchor_to_keys)


def chunk_canonical_keys(chunk_text: str, anchor_to_keys: dict[str, list[str]]) -> list[str]:
    """Find all canonical_keys whose anchor appears in this chunk."""
    n = normalize(chunk_text)
    keys: list[str] = []
    seen: set[str] = set()
    for anchor, ck_list in anchor_to_keys.items():
        if anchor in n:
            for ck in ck_list:
                if ck not in seen:
                    keys.append(ck)
                    seen.add(ck)
    return keys


# ─────────────────────────────────────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class QueryScore:
    query_id: str
    canonical_key: str
    source_family: str
    section_hit: bool  # any retrieved chunk maps to target canonical_key
    section_hit_rank: int | None  # 1-indexed rank of first matching chunk
    phrase_coverage: float  # fraction of required phrases found
    phrases_found: int
    phrases_total: int
    near_miss_count: int  # chunks from same book/file mapping to wrong canonical_key
    wrong_above_correct: bool  # near-miss outranks the target
    first_book_hit_rank: int | None  # rank of first chunk from target book
    chapter_hit: bool  # any chunk from same chapter_file
    diagnostics: list[str] = field(default_factory=list)
    retrieved_keys: list[str] = field(default_factory=list)  # for top-N debugging


def score_query(
    query: EvalQuery,
    retrieved: list[dict],
    anchor_to_keys: dict[str, list[str]],
) -> QueryScore:
    section_hit = False
    section_hit_rank: int | None = None
    near_miss_count = 0
    first_near_miss_rank: int | None = None
    chapter_hit = False
    first_book_hit_rank: int | None = None
    retrieved_keys: list[str] = []

    target_book = query.book

    for rank, hit in enumerate(retrieved, start=1):
        text = hit.get("text", "")
        chunk_chapter = hit.get("file") or hit.get("chapter_file") or ""
        # 简易 book 检测 — 用 file 路径前缀
        from_target_book = target_book and target_book in chunk_chapter
        from_target_file = query.chapter_file and query.chapter_file in chunk_chapter

        if from_target_book and first_book_hit_rank is None:
            first_book_hit_rank = rank
        if from_target_file:
            chapter_hit = True

        keys = chunk_canonical_keys(text, anchor_to_keys)
        # Some families (hehua) emit synthesized cards whose canonical_key is
        # NOT present in canonical_index.json — the anchor_to_keys grep cannot
        # see them. Trust hit["id"] as a direct canonical_key for those cases.
        hit_id = hit.get("id") or ""
        if hit_id and hit_id not in keys:
            keys = [*keys, hit_id]
        retrieved_keys.append(",".join(keys[:3]) or "—")

        if query.canonical_key in keys:
            if not section_hit:
                section_hit = True
                section_hit_rank = rank
        else:
            # 同家族返回的并行证据 (e.g. appearance 同时返回 gan + zhi) 不算 near-miss
            same_family_parallel = any(
                isinstance(k, str) and k.startswith(query.canonical_key.split("::")[0] + "::")
                for k in keys
            )
            in_explicit_near_miss = any(k in query.near_miss_keys for k in keys)
            if in_explicit_near_miss or (from_target_file and not same_family_parallel):
                near_miss_count += 1
                if first_near_miss_rank is None:
                    first_near_miss_rank = rank

    wrong_above_correct = (
        first_near_miss_rank is not None
        and (section_hit_rank is None or first_near_miss_rank < section_hit_rank)
    )

    # Phrase coverage on retrieved chunks
    union_text_norm = "\n".join(normalize(h.get("text", "")) for h in retrieved)
    found = sum(1 for p in query.required_phrases if p and p in union_text_norm)
    total = len([p for p in query.required_phrases if p])
    coverage = found / total if total else 0.0

    diagnostics: list[str] = []
    if not section_hit:
        diagnostics.append("MISSING_TARGET_SECTION")
    if section_hit and coverage < 0.5:
        diagnostics.append("SECTION_HIT_BUT_LOW_PHRASE_COVERAGE")
    if wrong_above_correct:
        diagnostics.append("WRONG_KEY_ABOVE_CORRECT")
    if not chapter_hit:
        diagnostics.append("MISSING_TARGET_FILE")
    if first_book_hit_rank and section_hit_rank and section_hit_rank > first_book_hit_rank + 2:
        diagnostics.append("CORRECT_BOOK_WRONG_SECTION_ORDER")

    return QueryScore(
        query_id=query.query_id,
        canonical_key=query.canonical_key,
        source_family=query.source_family,
        section_hit=section_hit,
        section_hit_rank=section_hit_rank,
        phrase_coverage=round(coverage, 3),
        phrases_found=found,
        phrases_total=total,
        near_miss_count=near_miss_count,
        wrong_above_correct=wrong_above_correct,
        first_book_hit_rank=first_book_hit_rank,
        chapter_hit=chapter_hit,
        diagnostics=diagnostics,
        retrieved_keys=retrieved_keys,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Aggregate
# ─────────────────────────────────────────────────────────────────────────────

def aggregate(scores: list[QueryScore]) -> dict:
    total = len(scores)
    if total == 0:
        return {"total": 0}

    section_hits = sum(1 for s in scores if s.section_hit)
    chapter_hits = sum(1 for s in scores if s.chapter_hit)
    avg_coverage = sum(s.phrase_coverage for s in scores) / total
    wrong_above = sum(1 for s in scores if s.wrong_above_correct)

    by_family: dict[str, list[QueryScore]] = defaultdict(list)
    for s in scores:
        by_family[s.source_family].append(s)

    diag_counts = Counter()
    for s in scores:
        for d in s.diagnostics:
            diag_counts[d] += 1

    family_stats = {}
    for fam, fs in by_family.items():
        n = len(fs)
        family_stats[fam] = {
            "n": n,
            "section_hit_rate": round(sum(1 for s in fs if s.section_hit) / n, 3),
            "chapter_hit_rate": round(sum(1 for s in fs if s.chapter_hit) / n, 3),
            "avg_phrase_coverage": round(sum(s.phrase_coverage for s in fs) / n, 3),
            "wrong_above_rate": round(sum(1 for s in fs if s.wrong_above_correct) / n, 3),
        }

    return {
        "total": total,
        "section_hit_rate": round(section_hits / total, 3),
        "chapter_hit_rate": round(chapter_hits / total, 3),
        "avg_phrase_coverage": round(avg_coverage, 3),
        "wrong_above_correct_rate": round(wrong_above / total, 3),
        "by_family": family_stats,
        "diagnostics": dict(diag_counts.most_common()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

async def _retrieve_legacy(query: EvalQuery, *, final_k: int, use_selector: bool) -> list[dict]:
    return await retrieve_for_chart(
        query.paipan,
        kind=query.intent_kind,
        user_message=query.user_question,
        final_k=final_k,
        use_selector=use_selector,
    )


async def _retrieve_phase_a(query: EvalQuery, *, final_k: int, use_selector: bool) -> list[dict]:
    """Phase A+B/C/E/F/H: family-specific deterministic / term-lookup retrievers.

    Each query has source_family ∈ {qtbj, smth, shensha, geju, liuqin,
    appearance, concept}; routed to its dedicated retriever. Output is
    converted to V1Hit dict so the legacy scorer works unchanged.
    """
    fam = query.source_family
    if fam == "qtbj":
        cards = await qtbj_retrieve(query.paipan, user_message=query.user_question)
    elif fam == "smth":
        cards = await smth89_retrieve(query.paipan, user_message=query.user_question)
    elif fam == "shensha":
        cards = await shensha_retrieve(query.paipan, user_message=query.user_question)
    elif fam == "geju":
        cards = await geju_retrieve(query.paipan, user_message=query.user_question)
    elif fam == "liuqin":
        cards = await liuqin_retrieve(query.paipan, user_message=query.user_question)
    elif fam == "appearance":
        cards = await appearance_retrieve(query.paipan, user_message=query.user_question)
    elif fam == "concept":
        cards = await concept_retrieve(query.paipan, user_message=query.user_question)
    elif fam == "theory":
        cards = await theory_retrieve(query.paipan, user_message=query.user_question)
    elif fam == "hehua":
        cards = await hehua_retrieve(query.paipan, user_message=query.user_question)
    else:
        cards = []
    return [c.to_v1_hit() for c in cards]


async def run_one(
    query: EvalQuery,
    *,
    final_k: int,
    use_selector: bool,
    anchor_to_keys: dict[str, list[str]],
    retriever: str = "legacy",
) -> tuple[QueryScore, list[dict]]:
    if retriever == "phase_a":
        retrieved = await _retrieve_phase_a(query, final_k=final_k, use_selector=use_selector)
    else:
        retrieved = await _retrieve_legacy(query, final_k=final_k, use_selector=use_selector)
    score = score_query(query, retrieved, anchor_to_keys)
    return score, retrieved


REGRESSION_QUERY_IDS = {"QTBJ_甲_丑", "SMTH_卷08_甲申_辛未"}


async def main_async(args: argparse.Namespace) -> int:
    canonical = json.loads(CANONICAL_INDEX_PATH.read_text(encoding="utf-8"))
    anchor_to_keys = build_chunk_canonical_map(canonical)
    logger.info("anchor table: %d anchors", len(anchor_to_keys))

    qtbj_queries = build_qtbj_queries(canonical)
    smth_queries = build_smth_queries(canonical)
    shensha_queries = build_shensha_queries(canonical)
    geju_queries = build_geju_queries(canonical)
    liuqin_queries = build_liuqin_queries(canonical)
    appearance_queries = build_appearance_queries(canonical)
    concept_queries = build_concept_queries(canonical)
    theory_queries = build_theory_queries(canonical)
    hehua_queries = build_hehua_queries(canonical)
    all_queries = (
        qtbj_queries + smth_queries
        + shensha_queries + geju_queries + liuqin_queries
        + appearance_queries + concept_queries
        + theory_queries
        + hehua_queries
    )

    if args.mode == "regression":
        queries = [q for q in all_queries if q.query_id in REGRESSION_QUERY_IDS]
        final_k = 6
        use_selector = True
    else:
        queries = all_queries
        if args.limit:
            queries = queries[:args.limit]
        final_k = 30
        use_selector = False

    logger.info("running %d queries (mode=%s, k=%d, selector=%s)",
                len(queries), args.mode, final_k, use_selector)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_{args.retriever}" if args.retriever != "legacy" else ""
    results_path = OUT_DIR / f"results_{args.mode}{suffix}.jsonl"
    summary_path = OUT_DIR / f"summary_{args.mode}{suffix}.json"

    scores: list[QueryScore] = []
    with results_path.open("w", encoding="utf-8") as fh:
        for i, q in enumerate(queries, 1):
            try:
                score, retrieved = await run_one(
                    q, final_k=final_k, use_selector=use_selector,
                    anchor_to_keys=anchor_to_keys,
                    retriever=args.retriever,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("query %s failed: %s", q.query_id, exc)
                continue
            scores.append(score)
            fh.write(json.dumps({
                "query": asdict(q),
                "score": asdict(score),
                "retrieved_top": [
                    {
                        "rank": idx + 1,
                        "source": h.get("source"),
                        "file": h.get("file"),
                        "id": h.get("id"),
                        "text_preview": (h.get("text") or "")[:80],
                    }
                    for idx, h in enumerate(retrieved[:10])
                ],
            }, ensure_ascii=False) + "\n")
            if i % 50 == 0:
                logger.info("  %d/%d done", i, len(queries))

    summary = aggregate(scores)
    summary["meta"] = {
        "mode": args.mode,
        "retriever": args.retriever,
        "final_k": final_k,
        "use_selector": use_selector,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "canonical_index_built_at": canonical.get("built_at"),
        "queries_attempted": len(queries),
        "queries_scored": len(scores),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("wrote %s", results_path)
    logger.info("wrote %s", summary_path)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["regression", "baseline"], default="baseline")
    parser.add_argument(
        "--retriever", choices=["legacy", "phase_a"], default="legacy",
        help="legacy = retrieval2 BM25+KG (+ optional selector); "
             "phase_a = retrieval3 family-specific deterministic lookup",
    )
    parser.add_argument("--limit", type=int, default=0,
                        help="cap number of queries (debug)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
