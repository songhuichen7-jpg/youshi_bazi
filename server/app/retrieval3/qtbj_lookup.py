"""穷通宝鉴 调候 deterministic lookup.

Given a chart, extracts (day_gan, month_zhi) and returns the canonical
QTBJ section as a single EvidenceCard. No BM25, no LLM, O(1) lookup.

Behavior:
* Exact (day_gan, month_zhi) hit → confidence=1.0
* Fallback section (源文按季节聚合,如三冬乙木) → confidence=0.6
* No paipan / missing fields → returns [] gracefully

The 120-cell table is loaded once via canonical_loader.qtbj_index().
"""
from __future__ import annotations

from typing import Any

from . import _chart
from .canonical_loader import qtbj_index
from .types import EvidenceCard


_QTBJ_GAN_TO_BOOK_LABEL = "穷通宝鉴"


def _format_source(section: dict) -> str:
    name = section.get("month_name") or ""
    day_gan = section.get("day_gan") or ""
    element = {"甲": "木", "乙": "木", "丙": "火", "丁": "火",
               "戊": "土", "己": "土", "庚": "金", "辛": "金",
               "壬": "水", "癸": "水"}.get(day_gan, "")
    if name and day_gan:
        return f"{_QTBJ_GAN_TO_BOOK_LABEL} · {name}{day_gan}{element}".strip()
    return _QTBJ_GAN_TO_BOOK_LABEL


def lookup(day_gan_: str, month_zhi_: str) -> EvidenceCard | None:
    if not day_gan_ or not month_zhi_:
        return None
    section = qtbj_index().get((day_gan_, month_zhi_))
    if section is None:
        return None
    confidence = 0.6 if section.get("fallback") else 1.0
    return EvidenceCard(
        canonical_key=section["canonical_key"],
        book=section["book"],
        source=_format_source(section),
        chapter_file=section["chapter_file"],
        text=section["text"],
        confidence=confidence,
        retriever="qtbj",
        claim_supported="tiaohou",
        metadata={
            "day_gan": day_gan_,
            "month_zhi": month_zhi_,
            "month_name": section.get("month_name"),
            "season_label": section.get("season_label"),
            "fallback": bool(section.get("fallback")),
            "paragraph_count": len(section.get("paragraphs") or []),
            "scope": section.get("month_name") or "full",
        },
    )


async def qtbj_retrieve(
    chart: dict[str, Any],
    *,
    user_message: str | None = None,
    k: int = 1,
) -> list[EvidenceCard]:
    """Module-level functional entry. ``k`` is accepted for protocol parity
    but ignored — this retriever returns 0 or 1 card."""
    card = lookup(_chart.day_gan(chart), _chart.month_zhi(chart))
    return [card] if card else []


class QtbjLookupRetriever:
    name = "qtbj"

    async def retrieve(
        self,
        chart: dict[str, Any],
        *,
        user_message: str | None = None,
        k: int = 1,
    ) -> list[EvidenceCard]:
        return await qtbj_retrieve(chart, user_message=user_message, k=k)
