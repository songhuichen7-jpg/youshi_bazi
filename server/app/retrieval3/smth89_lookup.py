"""三命通会 卷八/卷九 日时诀 deterministic lookup.

Given a chart, extracts (day_pillar, hour_pillar) and returns the canonical
日时 entry as a single EvidenceCard.

The 720-cell table (60 day pillars × 12 hour pillars) is loaded once via
canonical_loader.smth_index(). 6 entries are confirmed missing in the
source corpus (one explicitly marked 原闕) — those queries return [].
"""
from __future__ import annotations

from typing import Any

from . import _chart
from .canonical_loader import smth_index
from .types import EvidenceCard


_BOOK_LABEL = "三命通会"


def _format_source(entry: dict) -> str:
    volume = entry.get("volume") or ""
    day_pillar = entry.get("day_pillar") or ""
    hour_pillar = entry.get("hour_pillar") or ""
    if volume and day_pillar and hour_pillar:
        return f"{_BOOK_LABEL} · {volume} · {day_pillar}日{hour_pillar}时"
    return _BOOK_LABEL


def lookup(day_pillar_: str, hour_pillar_: str) -> EvidenceCard | None:
    if len(day_pillar_) != 2 or len(hour_pillar_) != 2:
        return None
    entry = smth_index().get((day_pillar_, hour_pillar_))
    if entry is None:
        return None
    return EvidenceCard(
        canonical_key=entry["canonical_key"],
        book=entry["book"],
        source=_format_source(entry),
        chapter_file=entry["chapter_file"],
        text=entry["text"],
        confidence=1.0,
        retriever="smth89",
        claim_supported="ri_shi",
        metadata={
            "volume": entry.get("volume"),
            "day_pillar": entry.get("day_pillar"),
            "hour_pillar": entry.get("hour_pillar"),
            "day_gan": entry.get("day_gan"),
            "day_zhi": entry.get("day_zhi"),
            "hour_zhi": entry.get("hour_zhi"),
            "section_heading": entry.get("section_heading"),
            "ocr_hour_gan": entry.get("ocr_hour_gan"),
            "scope": entry.get("section_heading") or "full",
        },
    )


async def smth89_retrieve(
    chart: dict[str, Any],
    *,
    user_message: str | None = None,
    k: int = 1,
) -> list[EvidenceCard]:
    card = lookup(_chart.day_pillar(chart), _chart.hour_pillar(chart))
    return [card] if card else []


class Smth89LookupRetriever:
    name = "smth89"

    async def retrieve(
        self,
        chart: dict[str, Any],
        *,
        user_message: str | None = None,
        k: int = 1,
    ) -> list[EvidenceCard]:
        return await smth89_retrieve(chart, user_message=user_message, k=k)
