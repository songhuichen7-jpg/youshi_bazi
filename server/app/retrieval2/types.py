"""Data contract.

Three core types you only need to read once:

* :class:`ClaimUnit`  — atomic 50-200 char piece of one classical text.
  Stable id derived from the source so re-running the indexer is reproducible.
* :class:`ClaimTags`  — what the LLM said this claim is about. Joined to
  the claim by ``claim_id``. Stored in a sibling JSONL.
* :class:`QueryIntent` — chart-derived "what we want to find". The retrieval
  core matches these against tags + text; nothing in the core knows BaZi.

Versions are bumped only when the on-disk shape or tagger prompt changes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

INDEX_SCHEMA_VERSION = "1"
"""Bump when ClaimUnit / ClaimTags fields change in a breaking way."""

TAGGER_PROMPT_VERSION = "2"
"""Bump when tagger prompt changes — forces re-tag.

v2 (2026-05-08): VOCAB[kind] gains 'judgement' and 'shensha'. Old indexes
with v1 tags load fine (refined_kind values are a subset of the new vocab),
but anyone wanting chunk_type-aware ranking should re-run the tagger.
"""

SPLITTER_VERSION = "2"
"""Bump when splitter algorithm changes — forces re-split.

v2 (2026-05-08): _detect_kind returns 'judgement' (绝对断语) and 'shensha'
(神煞类) where appropriate.
"""

ClaimKind = Literal[
    "principle",  # 抽象命题/原则:"先观月令"
    "rule",       # 带条件的规则:"正官格忌伤官刑冲" (alias-compatible with principle for now)
    "case",       # 具体命例:"如甲日庚午时…"
    "formula",    # 诀文/口诀体:"甲日X月為偏官" (alias-compatible with heuristic for now)
    "judgement",  # 绝对凶吉断语:"必贫必夭克妻刑子" — 降权
    "shensha",    # 神煞类:"桃花/驿马/天乙/孤辰/寡宿/空亡" — 降权
    "heuristic",  # 经验法则
    "meta",       # 篇首释例 / 表格行 — 不召回
    "unclear",    # 兜底
]


@dataclass(frozen=True, slots=True)
class ClaimUnit:
    """One atomic classical statement, 50-200 chars typically."""

    id: str
    """Stable: ``<book-key>.<chapter-stem>.<para-idx>[.<sent-idx>]``."""

    book: str
    chapter_file: str
    chapter_title: str
    section: str | None
    text: str
    paragraph_idx: int
    kind: ClaimKind = "principle"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClaimUnit:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass(frozen=True, slots=True)
class ClaimTags:
    """Structured metadata produced by the LLM tagger.

    Multi-valued fields are tuples of strings (controlled vocabulary —
    see ``tagger.VOCAB``). Empty tuple means "model said no signal here".
    """

    claim_id: str
    shishen: tuple[str, ...] = ()
    yongshen_method: tuple[str, ...] = ()
    day_strength: tuple[str, ...] = ()
    domain: tuple[str, ...] = ()
    season: tuple[str, ...] = ()
    day_gan: tuple[str, ...] = ()
    month_zhi: tuple[str, ...] = ()
    geju: tuple[str, ...] = ()
    refined_kind: ClaimKind = "principle"
    authority: float = 0.5
    tagger_version: str = TAGGER_PROMPT_VERSION
    tagger_model: str = ""
    tagger_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClaimTags:
        known = {f for f in cls.__dataclass_fields__}
        cleaned: dict[str, Any] = {}
        for k, v in d.items():
            if k not in known:
                continue
            if k in {"shishen", "yongshen_method", "day_strength", "domain",
                     "season", "day_gan", "month_zhi", "geju"}:
                cleaned[k] = tuple(v or ())
            else:
                cleaned[k] = v
        return cls(**cleaned)


@dataclass(frozen=True, slots=True)
class QueryIntent:
    """One reason to retrieve. Chart adapters emit a list; retrieval is
    divination-system agnostic.

    Semantics:
    * ``text`` feeds BM25 + selector context.
    * ``constraints[field]`` is OR within a field, AND across fields,
      matched against :class:`ClaimTags`.
    """

    text: str = ""
    constraints: dict[str, tuple[str, ...]] = field(default_factory=dict)
    weight: float = 1.0
    kind: str = "generic"


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    """One claim returned by :func:`service.retrieve_for_chart`, with
    provenance.

    Adapter to v1 dict shape lives in ``service.py``.
    """

    claim: ClaimUnit
    tags: ClaimTags
    score: float
    reason: str = ""
    """Free-form explanation from the selector for why this claim was picked.
    Useful for downstream observability; safe to ignore."""
    claim_supported: str = ""
    """Which sub-claim of the chart this evidence supports. Set by the
    selector; one of the intent kinds the chart adapter emitted (e.g.
    'tiaohou' / 'main_geju' / 'liu_qin.specific' / 'climate' / 'pattern' /
    'xingyun'). Empty when the selector did not assign one or when the
    fallback path is used. Downstream prompt rendering can group hits by
    this field so the LLM knows which sub-question each citation answers."""


__all__ = [
    "INDEX_SCHEMA_VERSION",
    "TAGGER_PROMPT_VERSION",
    "SPLITTER_VERSION",
    "ClaimKind",
    "ClaimUnit",
    "ClaimTags",
    "QueryIntent",
    "RetrievalHit",
]
