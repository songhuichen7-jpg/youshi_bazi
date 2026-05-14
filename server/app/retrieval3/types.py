"""Shared types for retrieval3 family retrievers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class EvidenceCard:
    """Unified retrieval output across all family retrievers.

    canonical_key uniquely identifies the evidence in the eval framework's
    canonical_index.json — one EvidenceCard ⇔ one canonical unit.
    """

    canonical_key: str
    book: str  # canonical book id, e.g. "qiongtong-baojian"
    source: str  # human-readable, e.g. "穷通宝鉴 · 十二月甲木"
    chapter_file: str
    text: str
    confidence: float = 1.0  # 0.0–1.0, deterministic lookups always 1.0
    retriever: str = ""  # "qtbj" / "smth89" / "shensha" / "theory"
    claim_supported: str = ""  # facet/claim this card answers
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_v1_hit(self) -> dict:
        """Adapter to retrieval2's V1Hit dict shape, for backwards-compat
        with existing eval scorers and chat injection sites."""
        return {
            "id": self.canonical_key,
            "source": self.source,
            "file": self.chapter_file,
            "scope": self.metadata.get("scope") or "full",
            "text": self.text,
            "chars": len(self.text),
            "claim_supported": self.claim_supported,
        }


@runtime_checkable
class Retriever(Protocol):
    """All family retrievers implement this minimal protocol."""

    name: str

    async def retrieve(
        self,
        chart: dict[str, Any],
        *,
        user_message: str | None = None,
        k: int = 1,
    ) -> list[EvidenceCard]:
        ...
