"""Pure-Python BM25 (Okapi).

The corpus is ~5k claims × ~150 chars; pure-Python suffices and adds zero
deps. Disk format: pickle of :class:`BM25Index`. Loadable in <50ms.

The structure is intentionally simple — if the project later adopts ``bm25s``
or ``rank-bm25``, the ``query`` API matches their surface so swapping is a
one-file change.
"""
from __future__ import annotations

import math
import pickle
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .tokenizer import encode, encode_query
from .tokenizer import fingerprint as tokenizer_fingerprint
from .types import ClaimUnit

BM25_VERSION = "2"
SECTION_TOKEN_REPEAT = 3  # boost section tokens by repeating them in the doc
DEFAULT_K1 = 1.5
DEFAULT_B = 0.75


@dataclass(slots=True)
class BM25Index:
    version: str = BM25_VERSION
    tokenizer_fingerprint: str = ""
    k1: float = DEFAULT_K1
    b: float = DEFAULT_B
    doc_ids: list[str] = field(default_factory=list)
    doc_lengths: list[int] = field(default_factory=list)
    avgdl: float = 0.0
    n_docs: int = 0
    df: dict[str, int] = field(default_factory=dict)
    postings: dict[str, list[tuple[int, int]]] = field(default_factory=dict)

    def _idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        if df == 0:
            return 0.0
        return math.log(1 + (self.n_docs - df + 0.5) / (df + 0.5))

    def query(self, text: str, k: int = 50) -> list[tuple[str, float]]:
        """Return ``[(claim_id, score), ...]`` sorted desc by score."""
        tokens = encode_query(text)
        if not tokens:
            return []
        scores: dict[int, float] = defaultdict(float)
        for term in set(tokens):
            postings = self.postings.get(term)
            if not postings:
                continue
            idf = self._idf(term)
            if idf <= 0:
                continue
            for doc_idx, tf in postings:
                dl = self.doc_lengths[doc_idx]
                norm = self.k1 * (1 - self.b + self.b * (dl / max(self.avgdl, 1.0)))
                scores[doc_idx] += idf * (tf * (self.k1 + 1)) / (tf + norm)
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]
        return [(self.doc_ids[i], s) for i, s in ranked]


def build_bm25(claims: Iterable[ClaimUnit]) -> BM25Index:
    """Build from claim stream. doc_idx == enumeration order."""
    doc_ids: list[str] = []
    doc_lengths: list[int] = []
    df: Counter[str] = Counter()
    postings: dict[str, list[tuple[int, int]]] = defaultdict(list)

    for doc_idx, claim in enumerate(claims):
        # Section title is a high-signal label (e.g. "六甲日戊辰時斷",
        # "論偏官") — fold its tokens into the doc with a repeat factor
        # so claims under a directly-matching section get a meaningful
        # tf boost vs. claims that only mention the term in passing.
        body_tokens = encode(claim.text)
        section_text = (getattr(claim, "section", "") or "").strip()
        section_tokens = encode(section_text) if section_text else []
        tokens = body_tokens + section_tokens * SECTION_TOKEN_REPEAT
        doc_ids.append(claim.id)
        doc_lengths.append(len(tokens))
        if not tokens:
            continue
        tf = Counter(tokens)
        for term, count in tf.items():
            df[term] += 1
            postings[term].append((doc_idx, count))

    n_docs = len(doc_ids)
    avgdl = sum(doc_lengths) / n_docs if n_docs else 0.0
    return BM25Index(
        version=BM25_VERSION,
        tokenizer_fingerprint=tokenizer_fingerprint(),
        doc_ids=doc_ids, doc_lengths=doc_lengths, avgdl=avgdl, n_docs=n_docs,
        df=dict(df), postings={t: lst for t, lst in postings.items()},
    )


def save_bm25(index: BM25Index, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        pickle.dump(index, fh, protocol=pickle.HIGHEST_PROTOCOL)


def load_bm25(path: Path) -> BM25Index | None:
    """Return ``None`` if missing or stale (version / tokenizer mismatch)."""
    if not path.exists():
        return None
    with path.open("rb") as fh:
        obj = pickle.load(fh)
    if not isinstance(obj, BM25Index):
        return None
    if obj.version != BM25_VERSION:
        return None
    if obj.tokenizer_fingerprint != tokenizer_fingerprint():
        return None
    return obj


__all__ = ["BM25_VERSION", "BM25Index", "build_bm25", "save_bm25", "load_bm25"]
