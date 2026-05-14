"""Claim-level classical-text retrieval (v2).

Public entry: :func:`service.retrieve_for_chart` — same async signature as
v1 (``app.retrieval.service.retrieve_for_chart``), so call sites switch via
a feature flag with no code change.
"""
from .types import (
    INDEX_SCHEMA_VERSION,
    SPLITTER_VERSION,
    TAGGER_PROMPT_VERSION,
    ClaimUnit,
    ClaimTags,
    QueryIntent,
    RetrievalHit,
)
from .normalize import normalize, expand, canonical, book_label
from .splitter import split_chapter, iter_classics
from .tokenizer import encode, encode_query
from .bm25 import build_bm25, save_bm25, load_bm25
from .kg import build_kg
from .intents import bazi_chart_to_intents
from .service import retrieve_for_chart, reset_cache

__all__ = [
    "INDEX_SCHEMA_VERSION",
    "SPLITTER_VERSION",
    "TAGGER_PROMPT_VERSION",
    "ClaimUnit",
    "ClaimTags",
    "QueryIntent",
    "RetrievalHit",
    "normalize",
    "expand",
    "canonical",
    "book_label",
    "split_chapter",
    "iter_classics",
    "encode",
    "encode_query",
    "build_bm25",
    "save_bm25",
    "load_bm25",
    "build_kg",
    "bazi_chart_to_intents",
    "retrieve_for_chart",
    "reset_cache",
]
