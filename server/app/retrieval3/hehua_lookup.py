"""地支合化 deterministic detection.

Scans the four earth branches (年/月/日/时) of a chart for:

* **三合 (full)** — 申子辰水, 亥卯未木, 寅午戌火, 巳酉丑金
* **半三合** — 任意含中神的两支 (e.g. 申子, 子辰 → 水)
* **三会方局** — 寅卯辰木, 巳午未火, 申酉戌金, 亥子丑水
* **六合** — (子丑) (寅亥) (卯戌) (辰酉) (巳申) (午未); v1 标存在不判化

Why this lives outside QtbjLookup / Geju:
* It is the single most impactful structural fact downstream synthesis
  routinely misses (see PM/specs analysis of the 1973 case where a 巳酉丑
  三合金 went unnoticed and led to "金 is 喜用" advice).
* The detection is pure earth-branch combinatorics — O(1) over a 4-tuple,
  no corpus chunks, no LLM. So it doesn't fit the term-driven / BM25
  retrievers and earns its own family.
* By always running (not gated on a 合 keyword in user_message), the
  evidence reaches the LLM even when the user asked an orthogonal question
  like "喜用什么五行".

The 古籍 reference text is short and stable — quoted inline below rather
than dragged through canonical_index.json. The chapter_file metadata still
points back to the real source for any reviewer who wants the full passage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import _chart
from .types import EvidenceCard


# ── 类型常量（导出供调用方匹配） ───────────────────────────────────────────

HEHUA_TYPE_TRIPLE_HE = "三合"
HEHUA_TYPE_HALF_TRIPLE = "半三合"
HEHUA_TYPE_TRIPLE_HUI = "三会"
HEHUA_TYPE_SIX_HE = "六合"


# ── 合化模式表 ─────────────────────────────────────────────────────────────

# 三合 (start, middle, end) — middle is the center / required branch for 半合
_TRIPLE_HE: list[tuple[tuple[str, str, str], str]] = [
    (("申", "子", "辰"), "水"),
    (("亥", "卯", "未"), "木"),
    (("寅", "午", "戌"), "火"),
    (("巳", "酉", "丑"), "金"),
]

# 三会方局 (东方木 etc) — order is contiguous on the zodiac
_TRIPLE_HUI: list[tuple[tuple[str, str, str], str]] = [
    (("寅", "卯", "辰"), "木"),
    (("巳", "午", "未"), "火"),
    (("申", "酉", "戌"), "金"),
    (("亥", "子", "丑"), "水"),
]

# 六合 — v1 不判化神 (古籍分歧大), 仅标存在
_SIX_HE: list[tuple[str, str]] = [
    ("子", "丑"),
    ("寅", "亥"),
    ("卯", "戌"),
    ("辰", "酉"),
    ("巳", "申"),
    ("午", "未"),
]


# ── 五行映射 ──────────────────────────────────────────────────────────────

_STEM_TO_ELEMENT: dict[str, str] = {
    "甲": "木", "乙": "木",
    "丙": "火", "丁": "火",
    "戊": "土", "己": "土",
    "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

# 我生 (day-master generates X)
_GEN_NEXT = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
# 我克 (day-master controls X)
_KE_NEXT = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}


def shishen_family(day_gan_: str, element: str) -> str | None:
    """Map an element to its 十神家族 relative to a day master.

    Returns one of: 比劫, 食伤, 财, 官杀, 印; or None if either input is
    invalid. We deliberately return the FAMILY (not the正/偏 split) because
    a 合化 produces an element wholesale, not a specific stem polarity.
    """
    dm = _STEM_TO_ELEMENT.get(day_gan_)
    if not dm or element not in _GEN_NEXT:
        return None
    if dm == element:
        return "比劫"
    if _GEN_NEXT[dm] == element:
        return "食伤"
    if _KE_NEXT[dm] == element:
        return "财"
    if _GEN_NEXT[element] == dm:
        return "印"
    if _KE_NEXT[element] == dm:
        return "官杀"
    return None


# ── 结果数据类 ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class HehuaResult:
    type: str  # one of the HEHUA_TYPE_* constants
    branches: tuple[str, ...]  # the matched earth branches (canonical order)
    element: str | None  # 化神五行; None for 六合 (v1 不判化)
    completeness: int  # 2 for 半三合 / 六合, 3 for 三合全 / 三会
    transparent: bool  # 化神是否透干
    transparent_stems: tuple[str, ...] = ()  # which stems carry the element
    shishen_family: str | None = None  # vs day master


# ── 检测主入口 ─────────────────────────────────────────────────────────────


def detect_hehua(chart: Any) -> list[HehuaResult]:
    """Pure-function detector. Returns all hehua patterns present in the
    chart's four earth branches, with 化神透干 status and 十神 family
    computed relative to the day master.

    Half-triple results are suppressed when a covering full 三合 fires for
    the same element — otherwise the LLM sees redundant evidence cards.
    """
    zhi = [z for z in _chart.four_zhi(chart) if z]
    gan = [g for g in _chart.four_gan(chart) if g]
    if not zhi:
        return []

    zhi_set = set(zhi)
    gan_elements = {_STEM_TO_ELEMENT.get(g) for g in gan}
    dm = _chart.day_gan(chart)
    results: list[HehuaResult] = []

    # 1. 三合全
    full_elements: set[str] = set()
    for trio, element in _TRIPLE_HE:
        if set(trio).issubset(zhi_set):
            transparent_stems = tuple(g for g in gan if _STEM_TO_ELEMENT.get(g) == element)
            results.append(HehuaResult(
                type=HEHUA_TYPE_TRIPLE_HE,
                branches=trio,
                element=element,
                completeness=3,
                transparent=element in gan_elements,
                transparent_stems=transparent_stems,
                shishen_family=shishen_family(dm, element),
            ))
            full_elements.add(element)

    # 2. 半三合 (含中神, 且未被全合覆盖)
    for trio, element in _TRIPLE_HE:
        if element in full_elements:
            continue  # suppress redundant half when full fires
        start, mid, end = trio
        for pair in [(start, mid), (mid, end)]:
            if set(pair).issubset(zhi_set):
                transparent_stems = tuple(g for g in gan if _STEM_TO_ELEMENT.get(g) == element)
                results.append(HehuaResult(
                    type=HEHUA_TYPE_HALF_TRIPLE,
                    branches=pair,
                    element=element,
                    completeness=2,
                    transparent=element in gan_elements,
                    transparent_stems=transparent_stems,
                    shishen_family=shishen_family(dm, element),
                ))

    # 3. 三会方局
    for trio, element in _TRIPLE_HUI:
        if set(trio).issubset(zhi_set):
            transparent_stems = tuple(g for g in gan if _STEM_TO_ELEMENT.get(g) == element)
            results.append(HehuaResult(
                type=HEHUA_TYPE_TRIPLE_HUI,
                branches=trio,
                element=element,
                completeness=3,
                transparent=element in gan_elements,
                transparent_stems=transparent_stems,
                shishen_family=shishen_family(dm, element),
            ))

    # 4. 六合 (v1 不判化)
    for pair in _SIX_HE:
        if set(pair).issubset(zhi_set):
            results.append(HehuaResult(
                type=HEHUA_TYPE_SIX_HE,
                branches=pair,
                element=None,
                completeness=2,
                transparent=False,
                transparent_stems=(),
                shishen_family=None,
            ))

    return results


# ── 古籍引用片段（固定, 短） ────────────────────────────────────────────

_REF_SAN_HE = (
    "《子平真诠·第七章》：「会者，三会也，申子辰之类是也」「三方为会，朋友之意也」。"
    "三支齐至，化神之气拉满整个地支底盘；若化神同时透干，则力量擂台中此五行的"
    "权重 = 透干 + 月令本气 + 三合加成，不能按单纯通根估算。"
)

_REF_HALF_HE = (
    "《子平真诠·第七章》以「会合」并论；半三合含中神时仍构成局气，但完整度弱于三合，"
    "通常视作「局气未足」——力量略弱于全合，仍需在力量擂台中显式标注。"
)

_REF_SAN_HUI = (
    "《子平真诠·第七章》：「三方为会」。三会方局为同方向之气聚合（东方木、南方火、"
    "西方金、北方水），力量较三合更纯粹方向化；若同时与三合并见，气势可能压倒月令本气。"
)

_REF_LIU_HE = (
    "《子平真诠·第七章》：「合者，六合也，子与丑合之类是也」「并对为合，比邻之意也」。"
    "六合化与不化历来分歧：必须月令支持化神五行 + 化神透干 + 无克制方为真化，否则"
    "属于「合而不化」——两支之间产生牵绊但不彻底转性。v1 仅标存在，化与不化的判定 "
    "应在力量擂台后由 §6.1 三条件 checklist 完成。"
)

# Map each hehua type to its reference chapter file + quote
_REF_BY_TYPE: dict[str, tuple[str, str]] = {
    HEHUA_TYPE_TRIPLE_HE: ("ziping-zhenquan/07_lun-xing-chong-hui-he-xie-fa.md", _REF_SAN_HE),
    HEHUA_TYPE_HALF_TRIPLE: ("ziping-zhenquan/07_lun-xing-chong-hui-he-xie-fa.md", _REF_HALF_HE),
    HEHUA_TYPE_TRIPLE_HUI: ("ziping-zhenquan/07_lun-xing-chong-hui-he-xie-fa.md", _REF_SAN_HUI),
    HEHUA_TYPE_SIX_HE: ("ziping-zhenquan/07_lun-xing-chong-hui-he-xie-fa.md", _REF_LIU_HE),
}


# ── EvidenceCard 输出 ─────────────────────────────────────────────────────


def _format_source(r: HehuaResult) -> str:
    branches = "".join(r.branches)
    if r.type == HEHUA_TYPE_TRIPLE_HE:
        return f"地支合化 · {branches}三合{r.element}局"
    if r.type == HEHUA_TYPE_HALF_TRIPLE:
        return f"地支合化 · {branches}半三合{r.element}"
    if r.type == HEHUA_TYPE_TRIPLE_HUI:
        return f"地支合化 · {branches}三会{r.element}局"
    return f"地支合化 · {branches}六合"


def _format_text(r: HehuaResult, ref_quote: str) -> str:
    lines: list[str] = []
    if r.element:
        head = f"【本盘检测】{''.join(r.branches)} {r.type}{r.element}局"
        if r.completeness == 3:
            head += "，完整度 3/3"
        elif r.completeness == 2:
            head += "，完整度 2/3"
        lines.append(head + "。")
    else:
        lines.append(f"【本盘检测】{''.join(r.branches)} {r.type}（v1 不判化神）。")

    if r.transparent and r.transparent_stems:
        stems = "、".join(r.transparent_stems)
        lines.append(f"化神透干：{stems}（化神{r.element}于天干显化）。")
    elif r.element:
        lines.append(f"化神{r.element}未透干（仅地支成局，气场存在但缺天干引出）。")

    if r.shishen_family:
        lines.append(f"相对日主十神家族：{r.shishen_family}。")

    lines.append("")
    lines.append(ref_quote)
    return "\n".join(lines)


def _to_card(r: HehuaResult) -> EvidenceCard:
    chapter_file, ref_quote = _REF_BY_TYPE[r.type]
    branches_join = "".join(r.branches)
    element_part = r.element or "无化"
    canonical_key = f"hehua::{branches_join}::{element_part}"
    return EvidenceCard(
        canonical_key=canonical_key,
        book="ziping-zhenquan",
        source=_format_source(r),
        chapter_file=chapter_file,
        text=_format_text(r, ref_quote),
        confidence=1.0,
        retriever="hehua",
        claim_supported="hehua_dizhi",
        metadata={
            "hehua_type": r.type,
            "branches": list(r.branches),
            "element": r.element,
            "completeness": f"{r.completeness}/3" if r.type in (
                HEHUA_TYPE_TRIPLE_HE, HEHUA_TYPE_TRIPLE_HUI,
            ) else f"{r.completeness}/2",
            "transparent": r.transparent,
            "transparent_stems": list(r.transparent_stems),
            "shishen_family": r.shishen_family,
            "scope": _format_source(r).split(" · ", 1)[-1],
        },
    )


async def hehua_retrieve(
    chart: dict[str, Any],
    *,
    user_message: str | None = None,
    k: int = 8,
) -> list[EvidenceCard]:
    """Module-level functional entry. ``user_message`` is unused — this
    retriever fires on every chart by design (the whole point is to surface
    structural facts the LLM does not know to ask for)."""
    if not isinstance(chart, dict) or not chart:
        return []
    results = detect_hehua(chart)
    cards = [_to_card(r) for r in results]
    # Defensive dedupe on canonical_key (should not collide in practice).
    seen: set[str] = set()
    unique: list[EvidenceCard] = []
    for c in cards:
        if c.canonical_key in seen:
            continue
        seen.add(c.canonical_key)
        unique.append(c)
    return unique[:k]


class HehuaRetriever:
    name = "hehua"

    async def retrieve(
        self,
        chart: dict[str, Any],
        *,
        user_message: str | None = None,
        k: int = 8,
    ) -> list[EvidenceCard]:
        return await hehua_retrieve(chart, user_message=user_message, k=k)


__all__ = [
    "HEHUA_TYPE_TRIPLE_HE",
    "HEHUA_TYPE_HALF_TRIPLE",
    "HEHUA_TYPE_TRIPLE_HUI",
    "HEHUA_TYPE_SIX_HE",
    "HehuaResult",
    "HehuaRetriever",
    "detect_hehua",
    "hehua_retrieve",
    "shishen_family",
]
