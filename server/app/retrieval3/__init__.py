"""Family-aware bazi retrieval (next gen).

Replaces the unified BM25+KG+selector pipeline of retrieval2 with a set of
family-specific retrievers:

* :class:`QtbjLookupRetriever` — 穷通宝鉴 调候 (10×12 deterministic table)
* :class:`Smth89LookupRetriever` — 三命通会卷八九 日时诀 (60×12 table)
* (future) ShenshaRetriever — 神煞词典
* (future) TheoryRetriever — 子平真诠/滴天髓 BM25+KG

Each retriever returns a list of :class:`EvidenceCard`. A composer (also
future) decides which retrievers to call based on intent + paipan.

Why parallel to retrieval2:
* Retrieval2 stays untouched while we validate Phase A on the eval
* Switch-over only after Phase A retrievers beat baseline by ≥4×
"""
from .types import EvidenceCard, Retriever  # noqa: F401
from .qtbj_lookup import QtbjLookupRetriever, qtbj_retrieve  # noqa: F401
from .smth89_lookup import Smth89LookupRetriever, smth89_retrieve  # noqa: F401
from .hehua_lookup import HehuaRetriever, hehua_retrieve, detect_hehua  # noqa: F401
from .term_retrievers import (  # noqa: F401
    ShenshaRetriever, shensha_retrieve,
    GejuRetriever, geju_retrieve,
    LiuqinRetriever, liuqin_retrieve,
    AppearanceRetriever, appearance_retrieve,
    ConceptRetriever, concept_retrieve,
    TheoryRetriever, theory_retrieve,
)
from .composer import compose  # noqa: F401
