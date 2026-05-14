"""Tokenizer for classical-Chinese BM25.

Recipe (deliberately simple, no jieba/transformers needed):

    1. variant-char fold (杀 ← 煞 ...) via :func:`normalize.normalize`
    2. char unigram + bigram (no trigram — keeps index small)
    3. on encode-side, also emit canonical synonym terms so 杀↔煞 collide

Symmetric: indexer and query use ``encode``; query side additionally calls
``encode_query`` to expand into all surface forms in each synonym class.
"""
from __future__ import annotations

import re
import unicodedata

from .normalize import canonical, expand, normalize, synonyms_version

TOKENIZER_VERSION = "1"

_PUNCT_RE = re.compile(
    r"[\s　、，。！？；：…—\-_/\\()（）\[\]【】《》〈〉<>\"'`~!@#$%^&*+=|]+"
)
_HAN_RE = re.compile(r"[㐀-鿿]")


def _han_segments(text: str) -> list[str]:
    """Split into runs of consecutive Han chars; drop punct/whitespace."""
    folded = unicodedata.normalize("NFKC", text)
    out: list[str] = []
    cursor = 0
    for m in _PUNCT_RE.finditer(folded):
        if m.start() > cursor:
            seg = folded[cursor:m.start()]
            if _HAN_RE.search(seg):
                out.append(seg)
        cursor = m.end()
    tail = folded[cursor:]
    if _HAN_RE.search(tail):
        out.append(tail)
    return out


def _ngrams(s: str, n_max: int = 2) -> list[str]:
    out: list[str] = []
    L = len(s)
    for n in range(1, n_max + 1):
        if n > L:
            break
        out.extend(s[i:i + n] for i in range(L - n + 1))
    return out


def encode(text: str) -> list[str]:
    """Index-side: variant-char fold → char 1-2 grams → synonym canonical
    extras."""
    folded = normalize(text)
    tokens: list[str] = []
    for seg in _han_segments(folded):
        tokens.extend(_ngrams(seg, n_max=2))
    if tokens:
        seen: set[tuple[str, str]] = set()
        for tok in list(tokens):
            cls = expand(tok)
            if len(cls) <= 1:
                continue
            canon = canonical(tok)
            if canon and canon != tok:
                key = (tok, canon)
                if key not in seen:
                    tokens.append(canon)
                    seen.add(key)
    return tokens


def encode_query(text: str) -> list[str]:
    """Query-side: same as ``encode`` plus every synonym-class member."""
    base = encode(text)
    if not base:
        return base
    expanded = list(base)
    seen = set(base)
    for tok in base:
        for syn in expand(tok):
            if syn and syn not in seen:
                expanded.append(syn)
                seen.add(syn)
    return expanded


def fingerprint() -> str:
    return f"tok-{TOKENIZER_VERSION}-syn-{synonyms_version()}"


__all__ = ["TOKENIZER_VERSION", "encode", "encode_query", "fingerprint"]
