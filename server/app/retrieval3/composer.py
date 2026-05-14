"""Retrieval3 composer — orchestrates family retrievers based on router intent.

Replaces retrieval2's single-pipeline ``retrieve_for_chart_compound`` with
intent-driven dispatch over the family retrievers in retrieval3 + a theory
fallback that delegates to retrieval2 for principle/case content not yet
covered by structured canonical units.

Caller contract
---------------
Single async entry ``compose()``:
    cards = await compose(chart, intent, secondary_intents, user_message,
                          retrieval_focus)
Returns ``list[EvidenceCard]`` (deduped, capped). Caller calls
``card.to_v1_hit()`` if it needs the legacy retrieval2 dict shape.

Why a composer
--------------
* QTBJ + SMTH 8/9 are deterministic table lookups that should ALWAYS run
  for 整体 / 命理类 query — BM25 cannot beat O(1) hash.
* Term-driven retrievers (shensha / concept / geju / liuqin) trigger when
  the user message OR retrieval_focus mentions the term. Cheap to always run.
* Appearance fires only on appearance/personality intent (otherwise noisy).
* Theory fallback hits retrieval2 with the **selector enabled** for the
  remaining ~4000 BM25-indexed chunks (子平真诠 论用神成败 / 滴天髓 各章 /
  渊海子平 诗赋等). This is the path that still uses the LLM selector.
"""
from __future__ import annotations

import logging
from typing import Any

from . import _chart
from .qtbj_lookup import qtbj_retrieve
from .smth89_lookup import smth89_retrieve
from .hehua_lookup import hehua_retrieve
from .term_retrievers import (
    appearance_retrieve,
    concept_retrieve,
    geju_retrieve,
    liuqin_retrieve,
    shensha_retrieve,
    theory_retrieve,
)
from .types import EvidenceCard

logger = logging.getLogger(__name__)


# 哪些 intent 触发哪些 retrievers — 维护成简表,后续按 router 实际意图分布扩
_INTENTS_WITH_TIAOHOU_AND_RISHI = frozenset({
    "meta", "verdict", "career", "wealth", "personality",
    "timing", "health", "relationship", "special_geju", "other",
})
_INTENTS_WITH_APPEARANCE = frozenset({"appearance", "personality"})
_INTENTS_FOR_THEORY_FALLBACK = frozenset({
    "meta", "verdict", "career", "wealth", "relationship", "timing",
    "personality", "health", "special_geju", "other",
})

_SKIP_INTENTS = frozenset({"chitchat", "divination", "media"})

_DEFAULT_MAX_CARDS = 8
_DEFAULT_THEORY_FALLBACK_K = 4


def _legacy_hit_to_card(hit: dict) -> EvidenceCard:
    file = hit.get("file") or hit.get("chapter_file") or ""
    book = file.split("/")[0] if file else ""
    cid = hit.get("id") or f"legacy::{file}::{(hit.get('text') or '')[:32]}"
    return EvidenceCard(
        canonical_key=cid,
        book=book,
        source=hit.get("source") or "",
        chapter_file=file,
        text=hit.get("text") or "",
        confidence=0.7,  # 不及确定性家族 (1.0),但比无引证强
        retriever="theory_legacy",
        claim_supported=hit.get("claim_supported") or "",
        metadata={"scope": hit.get("scope") or "full",
                  "chars": hit.get("chars")},
    )


def _normalize_intents(
    intent: str,
    secondary_intents: list[str] | None,
) -> set[str]:
    out: set[str] = set()
    for k in [intent, *(secondary_intents or [])]:
        if k and k not in _SKIP_INTENTS:
            out.add(k)
    return out


def _msg_for_terms(user_message: str | None, retrieval_focus: list[str] | None) -> str:
    parts: list[str] = []
    if user_message:
        parts.append(user_message)
    if retrieval_focus:
        parts.append(" ".join(retrieval_focus))
    return " ".join(parts)


async def compose(
    chart: dict[str, Any],
    *,
    intent: str,
    secondary_intents: list[str] | None = None,
    user_message: str | None = None,
    retrieval_focus: list[str] | None = None,
    max_cards: int = _DEFAULT_MAX_CARDS,
    enable_theory_fallback: bool = True,
    theory_fallback_k: int = _DEFAULT_THEORY_FALLBACK_K,
) -> list[EvidenceCard]:
    intents = _normalize_intents(intent, secondary_intents)
    if not intents:
        return []

    msg = _msg_for_terms(user_message, retrieval_focus)
    cards: list[EvidenceCard] = []

    # 1. 调候 + 日时 — 几乎所有命理 query 都受益, 0 LLM 成本
    if intents & _INTENTS_WITH_TIAOHOU_AND_RISHI:
        cards.extend(await qtbj_retrieve(chart, user_message=msg))
        cards.extend(await smth89_retrieve(chart, user_message=msg))

    # 1b. 地支合化 — 始终运行,不依赖 intent / user_msg。结构性事实,
    # synthesizer 漏看一次就会得到方向相反的喜用结论 (e.g. 巳酉丑三合金 →
    # 金已过旺却被误标为相神)
    cards.extend(await hehua_retrieve(chart))

    # 2. 格局 — 命盘已定格 OR user_msg 显式提到格名
    cards.extend(await geju_retrieve(chart, user_message=msg))

    # 3. 概念 — user_msg 含命理术语
    cards.extend(await concept_retrieve(chart, user_message=msg))

    # 4. 神煞 — user_msg 含神煞名
    cards.extend(await shensha_retrieve(chart, user_message=msg))

    # 5. 六亲 — user_msg 含 妻/夫/子/父/母 等
    cards.extend(await liuqin_retrieve(chart, user_message=msg))

    # 6. 外貌 — 限定 intent
    if intents & _INTENTS_WITH_APPEARANCE:
        cards.extend(await appearance_retrieve(chart, user_message=msg))

    # 7. 理论 — 主题字典 (Phase D), 75 个高频 topic
    cards.extend(await theory_retrieve(chart, user_message=msg, k=3))

    # 已被 retrieval3 高置信度家族覆盖的章节文件 — 用于 theory_legacy 兜底去重
    high_conf_files = {c.chapter_file for c in cards if c.chapter_file}

    # 8. 理论原则兜底 — 走 retrieval2 selector 路径,补未涵盖的原则/案例
    if enable_theory_fallback and intents & _INTENTS_FOR_THEORY_FALLBACK:
        try:
            from app.retrieval2.service import retrieve_for_chart_compound
            theory_kinds = sorted(intents & _INTENTS_FOR_THEORY_FALLBACK)[:3]
            legacy_hits = await retrieve_for_chart_compound(
                chart,
                kinds=theory_kinds,
                user_message=user_message,
                retrieval_focus=retrieval_focus,
                final_k=theory_fallback_k,
            )
            skipped_files = 0
            for h in legacy_hits or []:
                hit_file = h.get("file") or h.get("chapter_file") or ""
                # 已被 retrieval3 family 命中的同 chapter_file → 跳过,不重复占位
                if hit_file and hit_file in high_conf_files:
                    skipped_files += 1
                    continue
                cards.append(_legacy_hit_to_card(h))
            if skipped_files:
                logger.debug("composer dedup: skipped %d legacy hits already covered",
                             skipped_files)
        except Exception as exc:  # noqa: BLE001 — fallback 是 best-effort
            logger.warning("composer theory fallback failed: %s", exc)

    return _dedupe_and_cap(cards, max_cards=max_cards)


def _dedupe_and_cap(cards: list[EvidenceCard], *, max_cards: int) -> list[EvidenceCard]:
    """Dedupe by canonical_key (preserves first occurrence — preserves the
    intent-priority order from compose())."""
    seen: set[str] = set()
    out: list[EvidenceCard] = []
    for c in cards:
        key = c.canonical_key or f"_anon::{c.source}::{c.text[:24]}"
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= max_cards:
            break
    return out


__all__ = ["compose"]
