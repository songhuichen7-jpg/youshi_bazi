"""Tag-based reverse index ("KG").

In-memory inverted index built from ``ClaimTags`` at process start.
``constraint`` queries return ``{claim_id: score}`` where score = fraction
of constraint fields matched.

Tiny — ~200 lines combined with bm25.py.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from .normalize import canonical
from .types import ClaimTags

KG_FIELDS = (
    "shishen", "yongshen_method", "day_strength", "domain",
    "season", "day_gan", "month_zhi", "geju",
)


@dataclass(slots=True)
class KGIndex:
    field_index: dict[str, dict[str, set[str]]] = field(default_factory=dict)
    """``field -> term -> set(claim_id)``."""
    authority: dict[str, float] = field(default_factory=dict)

    def lookup(self, field_name: str, term: str) -> set[str]:
        return self.field_index.get(field_name, {}).get(term, set())

    def match(
        self,
        constraints: Mapping[str, tuple[str, ...]],
    ) -> dict[str, float]:
        """AND across fields, OR within. Score = fraction of fields matched."""
        active = [(k, vs) for k, vs in constraints.items()
                  if vs and k in self.field_index]
        if not active:
            return {}
        candidate_set: set[str] | None = None
        scores: dict[str, int] = defaultdict(int)
        for field_name, terms in active:
            field_hits: set[str] = set()
            for term in terms:
                field_hits |= self.lookup(field_name, term)
                field_hits |= self.lookup(field_name, canonical(term))
            for cid in field_hits:
                scores[cid] += 1
            candidate_set = field_hits if candidate_set is None else candidate_set & field_hits
            if not candidate_set:
                return {}
        denom = max(1, len(active))
        return {
            cid: scores.get(cid, 0) / denom + 0.05 * self.authority.get(cid, 0.0)
            for cid in (candidate_set or set())
        }


def build_kg(tags: Iterable[ClaimTags]) -> KGIndex:
    fi: dict[str, dict[str, set[str]]] = {f: defaultdict(set) for f in KG_FIELDS}
    auth: dict[str, float] = {}
    for tag in tags:
        cid = tag.claim_id
        auth[cid] = float(tag.authority or 0.0)
        for f in KG_FIELDS:
            for v in getattr(tag, f, ()) or ():
                if not v:
                    continue
                fi[f][v].add(cid)
                cv = canonical(v)
                if cv != v:
                    fi[f][cv].add(cid)
    return KGIndex(
        field_index={k: {t: set(ids) for t, ids in v.items()} for k, v in fi.items()},
        authority=auth,
    )


__all__ = ["KGIndex", "build_kg", "KG_FIELDS"]
