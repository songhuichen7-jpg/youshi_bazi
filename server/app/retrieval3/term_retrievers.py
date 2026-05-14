"""Term-based and chart-axis retrievers — Phase B/C/E/F/H.

Pattern shared by 5 family retrievers:
* Each canonical entry has a `term` (or `name` / `relation`) plus `aliases`
* Lookup keys come from EITHER user_message (term mention) OR chart fields
* Match is alias-aware substring; returns one EvidenceCard per matched entry

Keep these small and straightforward — the leverage is in the canonical
index quality (which is per-family hand-curated), not in retrieval cleverness.
"""
from __future__ import annotations

from typing import Any

from . import _chart
from .canonical_loader import (
    appearance_entries,
    appearance_index,
    concept_entries,
    geju_entries,
    liuqin_entries,
    shensha_entries,
    theory_entries,
)
from .types import EvidenceCard


def _alias_hits(message: str, aliases: list[str]) -> list[str]:
    if not message:
        return []
    return [a for a in aliases if a and a in message]


def _entry_to_card(
    entry: dict, *,
    name_key: str,
    canonical_label: str,
    retriever_name: str,
    claim_supported: str,
    matched_alias: str | None = None,
    confidence: float = 1.0,
) -> EvidenceCard:
    name = entry.get(name_key) or ""
    return EvidenceCard(
        canonical_key=entry["canonical_key"],
        book=entry.get("book") or "",
        source=f"{canonical_label}: {name}",
        chapter_file=entry.get("chapter_file") or (entry.get("chapter_files") or [""])[0],
        text=entry.get("text") or "",
        confidence=confidence,
        retriever=retriever_name,
        claim_supported=claim_supported,
        metadata={
            "name": name,
            "aliases": entry.get("aliases") or [],
            "matched_alias": matched_alias,
            "secondary_sources": entry.get("secondary_sources") or [],
            "chapter_files": entry.get("chapter_files") or [],
            "scope": entry.get("heading") or "full",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# 神煞 (Phase B) — term lookup in user_message
# ─────────────────────────────────────────────────────────────────────────────

async def shensha_retrieve(
    chart: dict[str, Any],
    *,
    user_message: str | None = None,
    k: int = 6,
) -> list[EvidenceCard]:
    msg = user_message or ""
    matched: list[tuple[dict, str]] = []
    seen: set[str] = set()
    for e in shensha_entries():
        hits = _alias_hits(msg, e.get("aliases") or [])
        if hits and e["canonical_key"] not in seen:
            matched.append((e, hits[0]))
            seen.add(e["canonical_key"])
    cards = [
        _entry_to_card(
            e, name_key="term", canonical_label="神煞",
            retriever_name="shensha", claim_supported="shensha",
            matched_alias=alias,
        )
        for e, alias in matched[:k]
    ]
    return cards


class ShenshaRetriever:
    name = "shensha"

    async def retrieve(self, chart, *, user_message=None, k=6):
        return await shensha_retrieve(chart, user_message=user_message, k=k)


# ─────────────────────────────────────────────────────────────────────────────
# 格局 (Phase C) — term lookup + chart.geju
# ─────────────────────────────────────────────────────────────────────────────

def _chart_geju_name(chart: dict) -> str | None:
    """Try to read chart's identified 格局 (when upstream已经定格)."""
    p = chart.get("PAIPAN") or chart.get("paipan") or chart
    if not isinstance(p, dict):
        return None
    obj = p.get("geJu") or p.get("ge_ju") or {}
    if not isinstance(obj, dict):
        return None
    main = obj.get("mainCandidate") or obj.get("main_candidate") or obj.get("main")
    if isinstance(main, dict):
        for key in ("name", "label", "geju", "geju_name"):
            v = main.get(key)
            if isinstance(v, str) and v:
                return v
    return None


async def geju_retrieve(
    chart: dict[str, Any],
    *,
    user_message: str | None = None,
    k: int = 6,
) -> list[EvidenceCard]:
    msg = user_message or ""
    cards: list[EvidenceCard] = []
    seen: set[str] = set()

    # 1. 用户消息显式提到 格局名
    for e in geju_entries():
        hits = _alias_hits(msg, e.get("aliases") or [])
        if hits and e["canonical_key"] not in seen:
            cards.append(_entry_to_card(
                e, name_key="name", canonical_label="格局",
                retriever_name="geju", claim_supported="geju",
                matched_alias=hits[0],
            ))
            seen.add(e["canonical_key"])

    # 2. 命盘已定格 (e.g. PAIPAN.geJu.mainCandidate)
    chart_name = _chart_geju_name(chart)
    if chart_name:
        for e in geju_entries():
            if e["canonical_key"] in seen:
                continue
            aliases = (e.get("aliases") or []) + [e.get("name") or ""]
            if any(a and a in chart_name for a in aliases):
                cards.append(_entry_to_card(
                    e, name_key="name", canonical_label="格局",
                    retriever_name="geju", claim_supported="geju",
                    matched_alias=chart_name,
                ))
                seen.add(e["canonical_key"])
                break

    return cards[:k]


class GejuRetriever:
    name = "geju"

    async def retrieve(self, chart, *, user_message=None, k=6):
        return await geju_retrieve(chart, user_message=user_message, k=k)


# ─────────────────────────────────────────────────────────────────────────────
# 六亲 (Phase E) — term lookup
# ─────────────────────────────────────────────────────────────────────────────

async def liuqin_retrieve(
    chart: dict[str, Any],
    *,
    user_message: str | None = None,
    k: int = 4,
) -> list[EvidenceCard]:
    msg = user_message or ""
    cards: list[EvidenceCard] = []
    seen: set[str] = set()
    for e in liuqin_entries():
        hits = _alias_hits(msg, e.get("aliases") or [])
        if hits and e["canonical_key"] not in seen:
            cards.append(_entry_to_card(
                e, name_key="relation", canonical_label="六亲",
                retriever_name="liuqin", claim_supported="liuqin",
                matched_alias=hits[0],
            ))
            seen.add(e["canonical_key"])
    return cards[:k]


class LiuqinRetriever:
    name = "liuqin"

    async def retrieve(self, chart, *, user_message=None, k=4):
        return await liuqin_retrieve(chart, user_message=user_message, k=k)


# ─────────────────────────────────────────────────────────────────────────────
# 外貌 (Phase F) — chart day_gan/day_zhi → 体象 + 性情相貌
# ─────────────────────────────────────────────────────────────────────────────

async def appearance_retrieve(
    chart: dict[str, Any],
    *,
    user_message: str | None = None,
    k: int = 3,
) -> list[EvidenceCard]:
    cards: list[EvidenceCard] = []
    seen: set[str] = set()

    idx = appearance_index()

    # day_gan 体象
    g = _chart.day_gan(chart)
    if g:
        e = idx.get(("gan", g))
        if e and e["canonical_key"] not in seen:
            cards.append(_entry_to_card(
                e, name_key="aspect", canonical_label=f"渊海子平 · 干支体象 · {g}干",
                retriever_name="appearance", claim_supported="appearance",
            ))
            seen.add(e["canonical_key"])

    # day_zhi 体象
    z = _chart.day_zhi(chart)
    if z:
        e = idx.get(("zhi", z))
        if e and e["canonical_key"] not in seen:
            cards.append(_entry_to_card(
                e, name_key="aspect", canonical_label=f"渊海子平 · 干支体象 · {z}支",
                retriever_name="appearance", claim_supported="appearance",
            ))
            seen.add(e["canonical_key"])

    # general 性情相貌 (always include)
    general = idx.get(("general", "general"))
    if general and general["canonical_key"] not in seen:
        cards.append(_entry_to_card(
            general, name_key="aspect", canonical_label="三命通会 · 论性情相貌",
            retriever_name="appearance", claim_supported="appearance",
        ))
        seen.add(general["canonical_key"])

    return cards[:k]


class AppearanceRetriever:
    name = "appearance"

    async def retrieve(self, chart, *, user_message=None, k=3):
        return await appearance_retrieve(chart, user_message=user_message, k=k)


# ─────────────────────────────────────────────────────────────────────────────
# 概念 (Phase H) — term lookup
# ─────────────────────────────────────────────────────────────────────────────

async def concept_retrieve(
    chart: dict[str, Any],
    *,
    user_message: str | None = None,
    k: int = 4,
) -> list[EvidenceCard]:
    msg = user_message or ""
    cards: list[EvidenceCard] = []
    seen: set[str] = set()

    # term/aliases 长度排序: 优先匹配长 alias (避免 "正官" 短词把 "正官格"
    # 类的歧义截断)
    sorted_entries = sorted(
        concept_entries(),
        key=lambda e: -max((len(a) for a in (e.get("aliases") or [])), default=0),
    )
    for e in sorted_entries:
        hits = _alias_hits(msg, e.get("aliases") or [])
        if hits and e["canonical_key"] not in seen:
            cards.append(_entry_to_card(
                e, name_key="term", canonical_label="概念",
                retriever_name="concept", claim_supported="concept",
                matched_alias=hits[0],
            ))
            seen.add(e["canonical_key"])
    return cards[:k]


class ConceptRetriever:
    name = "concept"

    async def retrieve(self, chart, *, user_message=None, k=4):
        return await concept_retrieve(chart, user_message=user_message, k=k)


# ─────────────────────────────────────────────────────────────────────────────
# 理论 (Phase D) — topic bundle lookup
# ─────────────────────────────────────────────────────────────────────────────
# 跟 concept 的 difference: theory entries 是大段原则论述 (~500-2000 字),
# 数量多 (~75),命中后通常返回 1-2 张。alias-driven term match,优先长 alias。

async def theory_retrieve(
    chart: dict[str, Any],
    *,
    user_message: str | None = None,
    k: int = 3,
) -> list[EvidenceCard]:
    msg = user_message or ""
    cards: list[EvidenceCard] = []
    seen: set[str] = set()

    # 长 alias 优先匹配,避免短 alias 把更具体的 topic 截走
    sorted_entries = sorted(
        theory_entries(),
        key=lambda e: -max((len(a) for a in (e.get("aliases") or [])), default=0),
    )
    for e in sorted_entries:
        hits = _alias_hits(msg, e.get("aliases") or [])
        if hits and e["canonical_key"] not in seen:
            cards.append(_entry_to_card(
                e, name_key="topic", canonical_label="理论",
                retriever_name="theory", claim_supported="theory",
                matched_alias=hits[0],
            ))
            seen.add(e["canonical_key"])
            if len(cards) >= k:
                break
    return cards


class TheoryRetriever:
    name = "theory"

    async def retrieve(self, chart, *, user_message=None, k=3):
        return await theory_retrieve(chart, user_message=user_message, k=k)


__all__ = [
    "shensha_retrieve", "ShenshaRetriever",
    "geju_retrieve", "GejuRetriever",
    "liuqin_retrieve", "LiuqinRetriever",
    "appearance_retrieve", "AppearanceRetriever",
    "concept_retrieve", "ConceptRetriever",
    "theory_retrieve", "TheoryRetriever",
]
