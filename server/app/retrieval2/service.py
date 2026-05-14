"""Public entry — drop-in replacement for ``app.retrieval.service``.

Same async signature as v1 (``retrieve_for_chart(chart, kind, user_message)
-> list[V1Hit]``) so call sites are unchanged.

Pipeline at runtime:

    intents = bazi_chart_to_intents(chart, kind, user_msg)
    candidates = BM25(text-of-intents) ∪ KG(constraints-of-intents)  → top 30
    hits = await DeepSeek_select(chart, intents, user_msg, candidates)  → 6
    return [v1_shape(h) for h in hits]

Failure modes are graceful:
* No index on disk → return [] (caller falls back to v1)
* Selector LLM error → fall back to top-k by fused score
"""
from __future__ import annotations

import logging
import os
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, TypedDict

from . import bm25 as bm25_mod
from . import kg as kg_mod
from . import selector as selector_mod
from . import storage
from .intents import bazi_chart_to_intents
from .normalize import book_label
from .policy import RetrievalPolicy, build_policy
from .types import ClaimTags, ClaimUnit, RetrievalHit
from .types import QueryIntent

logger = logging.getLogger(__name__)

DEFAULT_FUSED_TOP_N = 30
DEFAULT_FINAL_K = 6


class V1Hit(TypedDict, total=False):
    """Mirrors ``app.retrieval.service.RetrievalHit`` (TypedDict).

    The 5 base fields (source/file/scope/chars/text) are always set.
    ``claim_supported`` is set when the selector tagged this hit with
    one of the chart-derived intent kinds (e.g. 'tiaohou', 'main_geju',
    'pattern', 'climate', 'xingyun.*'). Empty string when missing — old
    callers that only look at the base 5 fields continue to work."""

    id: str
    source: str
    file: str
    scope: str
    chars: int
    text: str
    claim_supported: str


def _default_index_root() -> Path:
    env = os.environ.get("RETRIEVAL2_INDEX_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "var" / "retrieval2"


@lru_cache(maxsize=4)
def _bundle(root_str: str):
    root = Path(root_str)
    p = storage.paths(root)
    claims = {c.id: c for c in storage.load_claims(p.claims)}
    tags = {t.claim_id: t for t in storage.load_tags(p.tags)}
    bm25_idx = bm25_mod.load_bm25(p.bm25) if p.bm25.exists() else None
    kg_idx = kg_mod.build_kg(tags.values())
    logger.info(
        "retrieval2 loaded: %d claims, %d tags, bm25=%s, kg fields=%d",
        len(claims), len(tags), bool(bm25_idx), len(kg_idx.field_index),
    )
    if bm25_idx is None and claims:
        # BM25 silently falling back to KG-only is the most common cause of
        # mysterious recall regressions after pulling new code (tokenizer
        # fingerprint changed → load_bm25 returned None → BM25 channel off,
        # but the rest of retrieval keeps working). Fail loud so devs notice.
        logger.error(
            "retrieval2 BM25 index is missing or stale at %s — BM25 channel "
            "is OFF (KG + policy only). Rebuild with: "
            "uv run --package server python -m server.scripts.build_classics_index --no-tag",
            p.bm25,
        )
    return claims, tags, bm25_idx, kg_idx


def reset_cache() -> None:
    """For tests / index rebuild."""
    _bundle.cache_clear()


def _v1_shape(hit: RetrievalHit) -> V1Hit:
    # Some books store chapter_title with the book name already prefixed
    # (e.g. 三命通会 · 卷四). Avoid emitting "三命通会 · 三命通会 · 卷四".
    book = book_label(hit.claim.book) or ""
    chapter = hit.claim.chapter_title or ""
    if book and chapter.startswith(book):
        source = chapter
    else:
        source = " · ".join(p for p in (book, chapter) if p)
    return V1Hit(
        id=hit.claim.id,
        source=source,
        file=hit.claim.chapter_file,
        scope=hit.claim.section or "full",
        text=hit.claim.text,
        chars=len(hit.claim.text),
        claim_supported=hit.claim_supported,
    )


def _planner_focus_intents(retrieval_focus: list[str] | tuple[str, ...] | None) -> list[QueryIntent]:
    if not retrieval_focus:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in retrieval_focus:
        text = " ".join(str(item or "").split())[:24]
        if not text or text in seen:
            continue
        cleaned.append(text)
        seen.add(text)
        if len(cleaned) >= 8:
            break
    if not cleaned:
        return []
    return [
        QueryIntent(
            text=" ".join(cleaned),
            constraints={},
            weight=0.9,
            kind="planner.focus",
        )
    ]


def _gather_candidates(
    intents,
    bm25_idx,
    kg_idx,
    claims: dict[str, ClaimUnit],
    tags: dict[str, ClaimTags],
    *,
    n: int,
    policy: RetrievalPolicy,
) -> dict[str, dict[str, float]]:
    """Run BM25 + KG on each intent; aggregate per-claim per-channel score."""
    scores: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for intent in intents:
        if intent.text and bm25_idx is not None:
            for cid, s in bm25_idx.query(intent.text, k=n):
                scores[cid]["bm25"] += s * intent.weight
        if intent.constraints:
            for cid, s in kg_idx.match(intent.constraints).items():
                scores[cid]["kg"] += s * intent.weight
    for cid, claim in claims.items():
        tag = tags.get(cid, ClaimTags(claim_id=cid))
        if policy.rejects(claim, tag):
            scores[cid]["reject"] = 1.0
            continue
        boost = policy.boost(claim, tag)
        if boost > 0:
            scores[cid]["policy"] += boost
    return scores


def _fuse(
    scores: dict[str, dict[str, float]],
    *,
    n: int,
) -> list[tuple[str, float, dict[str, float]]]:
    """Tiny linear blend across channels — only used to pre-filter to N
    candidates before the selector. Selector does the real ranking, so this
    just needs to keep the right candidates in the pool."""
    max_bm25 = max((ch.get("bm25", 0.0) for ch in scores.values()), default=0.0)
    usable = [ch for ch in scores.values() if not ch.get("reject")]
    max_kg = max((ch.get("kg", 0.0) for ch in usable), default=0.0)
    max_policy = max((ch.get("policy", 0.0) for ch in usable), default=0.0)
    out: list[tuple[str, float, dict[str, float]]] = []
    for cid, ch in scores.items():
        if ch.get("reject"):
            continue
        # Normalize each channel by its own max within this query so the
        # blend doesn't get dominated by one channel's scale.
        bm25 = ch.get("bm25", 0.0) / max_bm25 if max_bm25 > 0 else 0.0
        kg = ch.get("kg", 0.0) / max_kg if max_kg > 0 else 0.0
        policy = ch.get("policy", 0.0) / max_policy if max_policy > 0 else 0.0
        fused = 0.35 * bm25 + 1.0 * kg + 1.35 * policy
        out.append((cid, fused, dict(ch)))
    out.sort(key=lambda x: x[1], reverse=True)
    return out[:n]


def _promote_preferred_files(
    fused: list[tuple[str, float, dict[str, float]]],
    claims: dict[str, ClaimUnit],
    policy: RetrievalPolicy,
    *,
    n: int,
) -> list[tuple[str, float, dict[str, float]]]:
    if not policy.preferred_files:
        return fused[:n]

    anchors: list[tuple[str, float, dict[str, float]]] = []
    for file_name in policy.preferred_files:
        match = next(
            (item for item in fused if claims.get(item[0]) and claims[item[0]].chapter_file == file_name),
            None,
        )
        if match is not None:
            anchors.append(match)

    out: list[tuple[str, float, dict[str, float]]] = []
    seen: set[str] = set()
    for item in [*anchors, *fused]:
        cid = item[0]
        if cid in seen:
            continue
        out.append(item)
        seen.add(cid)
        if len(out) >= n:
            break
    return out


def _diversify_fused(
    fused: list[tuple[str, float, dict[str, float]]],
    claims: dict[str, ClaimUnit],
    *,
    n: int,
    per_section: int = 1,
    per_file: int = 4,
) -> list[tuple[str, float, dict[str, float]]]:
    """Dedup the candidate pool by (chapter_file, section) and cap per chapter_file.

    Per-section cap kills the "two paragraphs from the same passage" case
    (e.g. two segments of 穷通宝鉴·三秋甲木) without losing meaningfully
    distinct sections within the same file (e.g. 三命通会 卷四 has 申月,
    酉月, 论甲乙, 甲乙 — these are different topics in one file)."""
    if per_section <= 0:
        return fused[:n]

    section_counts: dict[tuple[str, str], int] = defaultdict(int)
    file_counts: dict[str, int] = defaultdict(int)
    out: list[tuple[str, float, dict[str, float]]] = []
    seen: set[str] = set()

    for item in fused:
        cid = item[0]
        claim = claims.get(cid)
        if claim is None:
            continue
        sec_key = (claim.chapter_file, claim.section or "_full_")
        if section_counts[sec_key] >= per_section:
            continue
        if file_counts[claim.chapter_file] >= per_file:
            continue
        out.append(item)
        seen.add(cid)
        section_counts[sec_key] += 1
        file_counts[claim.chapter_file] += 1
        if len(out) >= n:
            return out

    return out


_BM25_ANCHOR_INTENT_KINDS = frozenset({
    "combo.day_hour", "user_msg", "liu_qin.specific",
    "combo.gan_xiang", "combo.nv_ming", "shen_sha.overview",
    "combo.current_yun",
})

# 锚位优先级 — 数字越小越靠前。combo.day_hour 之类高度具体的诀文匹配
# 应该排在 user_msg 之前，否则用户随便一句"我的财运怎么样"的 BM25 命中
# 会把"甲日戊辰時 时上偏财"这种字面命名的诀文挤出最终 K 条。
_ANCHOR_KIND_PRIORITY: dict[str, int] = {
    "combo.day_hour": 0,
    "combo.gan_xiang": 1,
    "combo.nv_ming": 2,
    "combo.current_yun": 3,
    "liu_qin.specific": 4,
    # shen_sha.<term> → 5 (handled below)
    "shen_sha.overview": 5,
    "user_msg": 99,
}


def _is_bm25_anchor_kind(kind: str) -> bool:
    """Match exact kinds plus the dynamic ``shen_sha.<term>`` variants."""
    return kind in _BM25_ANCHOR_INTENT_KINDS or kind.startswith("shen_sha.")


def _anchor_kind_rank(kind: str) -> int:
    if kind.startswith("shen_sha."):
        return 5
    return _ANCHOR_KIND_PRIORITY.get(kind, 50)


def _promote_bm25_anchors(
    fused: list[tuple[str, float, dict[str, float]]],
    claims: dict[str, ClaimUnit],
    bm25_idx,
    intents,
    policy: RetrievalPolicy | None = None,
    *,
    n: int,
    per_intent_k: int = 2,
) -> list[tuple[str, float, dict[str, float]]]:
    """Reserve slots in the candidate pool for top BM25 hits of high-signal
    pure-text intents (user question, day-pillar + hour-pillar combos).

    The fused score weights BM25 at 0.35 and KG/policy higher, which is the
    right call for the typical 格局/月令/十神 retrieval — but it buries text
    matches that have **no** structural tag overlap. The classic example:
    三命通会 卷八/卷九 organise advice by 六X日Y時 catalogs, and ClaimTags
    has no hour_pillar field, so those entries can only ever surface via
    BM25 text match. Without this anchor, "甲日戊辰時 偏财" queries lose
    to generic 财 essays despite being a literal substring match.

    Idempotent: anchors that are already in ``fused`` are not duplicated.

    Anchor 不能 outrank policy.preferred_files / preferred_file_fragments
    --------------------------------------------------------------------
    历史 bug：anchor 被赋成 top_fused_score 然后插到 ``out`` 头部，因为
    insertion order 决定 ``use_selector=False`` 路径的最终排序，policy
    精挑出来的"夫妻 / 何知章 / 论行运"被 三命通会 anchor 一句"甲日壬申时"
    顶下来。test_relationship_prefers_spouse_not_children 等 4 条专门 pin
    住的失败用例就是这个 — 连续 N 个月 4 fail 没人收。

    修法：
      1. 跳过 policy.rejects 的 anchor（policy 已经说"这个文件错主题"，
         BM25 文本巧合不该把它救回来）
      2. anchor 留 ``policy.preferred_files`` / ``preferred_file_fragments``
         匹配的"主力位"在最前；anchor 滑到主力之后、其它 fused 之前
    """
    if bm25_idx is None or not intents:
        return fused[:n]

    # 按 anchor 优先级排序后再遍历，让具体诀文（combo.day_hour 等）的
    # 命中先入池，user_msg 兜底锚最后入。这样在尾段被 _ensure_preferred_hits
    # 截断时，留下来的最末条也是高信号的具体匹配，不是 generic 文本搜。
    anchor_intents = [it for it in intents if _is_bm25_anchor_kind(it.kind) and it.text]
    anchor_intents.sort(key=lambda it: _anchor_kind_rank(it.kind))
    anchor_entries: list[tuple[str, str, str]] = []
    seen_ids: set[str] = set()
    for it in anchor_intents:
        for cid, _score in bm25_idx.query(it.text, k=per_intent_k):
            if cid not in claims or cid in seen_ids:
                continue
            # 跳过 policy 已经显式拒绝的 anchor — 说"夫妻"问题不要 zi-nv
            # 章节的话，BM25 别拐弯把 zi-nv 救回来。无 policy（None）时
            # 退回原行为兼容老调用方。
            if policy is not None:
                # rejects 需要 tags；这里没有 tags 字典，但 policy.rejects
                # 容许传入空 tags 仍然能基于文件名拒绝
                from .types import ClaimTags as _T
                if policy.rejects(claims[cid], _T(claim_id=cid)):
                    continue
            anchor_entries.append((cid, it.kind, it.text))
            seen_ids.add(cid)

    if not anchor_entries:
        return fused[:n]

    fused_by_id = {item[0]: item for item in fused}
    # 给 anchor 一个不低于"当前 top fused_score"的保底分。原因：
    # selector LLM 失败时会 fall back 到按 fused_score 排序的 _topup，
    # 而我们靠的是把 anchor 放到列表前面的"位置语义"。如果 fused_score
    # 太低（比如 0.35 = 单独 BM25 通道贡献），_topup 会把它排到 KG 富
    # 的条目下面 → 又一次绕过锚位。
    # 把 anchor 抬到 top fused_score 等高（不超过它），保证 sort 稳定后
    # anchor 仍然在 top 区，且不会超过原本 KG/policy 双高的"主力"条目。
    top_fused_score = max((s for _, s, _ in fused), default=1.0)

    # 算 policy "主力位" — 已经在 fused 里且匹配 preferred_files /
    # preferred_file_fragments 的条目。这些不能被 anchor 顶下来。
    main_seats: list[tuple[str, float, dict[str, float]]] = []
    main_files: set[str] = set()
    if policy is not None and (policy.preferred_files or policy.preferred_file_fragments):
        for item in fused:
            cid = item[0]
            claim = claims.get(cid)
            if claim is None:
                continue
            file_name = claim.chapter_file
            if file_name in main_files:
                continue
            if file_name in policy.preferred_files or any(
                frag in file_name for frag in policy.preferred_file_fragments
            ):
                main_seats.append(item)
                main_files.add(file_name)

    out: list[tuple[str, float, dict[str, float]]] = []
    placed: set[str] = set()

    # 财运问题里，如果时柱本身就是财星，combo.day_hour 命中的《三命通会》
    # 日时断辞比通用财章更贴盘面。把这类盘面专属锚点放到首位，避免主
    # 回答只引用「何知章 / 论财」而漏掉“甲戌日戊辰时大富”这种直指原局
    # 的证据；非财星时柱仍保持主力财章优先，免得杂泛日时诀文抢位。
    front_anchor_ids = [
        cid for cid, kind, text in anchor_entries
        if policy is not None
        and policy.kind == "wealth"
        and kind == "combo.day_hour"
        and "财" in text
    ]
    for cid in front_anchor_ids:
        existing = fused_by_id.get(cid)
        if existing is not None:
            base_score, meta = existing[1], dict(existing[2])
        else:
            base_score, meta = 0.0, {}
        meta["bm25_anchor"] = 1.0
        meta["bm25_front_anchor"] = 1.0
        anchor_score = max(base_score, top_fused_score)
        out.append((cid, anchor_score, meta))
        placed.add(cid)
        if len(out) >= n:
            return out

    # 主力位先占（policy 算出的 winner），anchor 排到主力之后
    for item in main_seats:
        if item[0] in placed:
            continue
        out.append(item)
        placed.add(item[0])
        if len(out) >= n:
            return out

    for cid, _kind, _text in anchor_entries:
        if cid in placed:
            continue
        existing = fused_by_id.get(cid)
        if existing is not None:
            base_score, meta = existing[1], dict(existing[2])
        else:
            base_score, meta = 0.0, {}
        meta["bm25_anchor"] = 1.0
        anchor_score = max(base_score, top_fused_score)
        out.append((cid, anchor_score, meta))
        placed.add(cid)
        if len(out) >= n:
            return out

    for item in fused:
        if item[0] in placed:
            continue
        out.append(item)
        if len(out) >= n:
            break
    return out


def _ensure_preferred_hits(
    hits: list[RetrievalHit],
    candidates: list[selector_mod.Candidate],
    policy: RetrievalPolicy,
    *,
    k: int,
) -> list[RetrievalHit]:
    if not policy.preferred_files or not candidates:
        return hits[:k]

    by_file: dict[str, selector_mod.Candidate] = {}
    for c in candidates:
        by_file.setdefault(c.claim.chapter_file, c)

    out: list[RetrievalHit] = []
    seen: set[str] = set()
    by_hit_id = {h.claim.id: h for h in hits}

    for c in candidates:
        if not (c.meta or {}).get("bm25_front_anchor"):
            continue
        hit = by_hit_id.get(c.claim.id) or RetrievalHit(
            claim=c.claim,
            tags=c.tags,
            score=c.fused_score,
            reason="specific-anchor",
        )
        out.append(hit)
        seen.add(hit.claim.id)
        if len(out) >= k:
            return out

    for file_name in policy.preferred_files:
        c = by_file.get(file_name)
        if c is None:
            continue
        hit = by_hit_id.get(c.claim.id) or RetrievalHit(
            claim=c.claim,
            tags=c.tags,
            score=c.fused_score,
            reason="preferred-source",
        )
        out.append(hit)
        seen.add(hit.claim.id)
        if len(out) >= k:
            return out

    for hit in hits:
        if hit.claim.id in seen:
            continue
        out.append(hit)
        seen.add(hit.claim.id)
        if len(out) >= k:
            break
    return out


async def retrieve_for_chart(
    chart: dict[str, Any],
    kind: str,
    user_message: str | None = None,
    *,
    retrieval_focus: list[str] | tuple[str, ...] | None = None,
    index_root: Path | None = None,
    final_k: int = DEFAULT_FINAL_K,
    fused_top_n: int = DEFAULT_FUSED_TOP_N,
    use_selector: bool = True,
) -> list[V1Hit]:
    """v1-compatible signature. Returns v1-shaped dicts.

    Internal pipeline:
      1. chart → intents
      2. BM25 + KG → top fused_top_n candidates
      3. DeepSeek selector → up to final_k (graceful fallback to fused score)
      4. v1 dict shape
    """
    intent_kind = kind[len("section:"):] if kind.startswith("section:") else kind
    intents = bazi_chart_to_intents(chart, intent_kind, user_message)
    intents = [*_planner_focus_intents(retrieval_focus), *intents]
    if not intents:
        return []
    policy = build_policy(chart, intent_kind, user_message)
    claims, tags, bm25_idx, kg_idx = _bundle(
        str((index_root or _default_index_root()).resolve())
    )
    if not claims:
        logger.warning("retrieval2 index empty — returning []")
        return []

    raw_scores = _gather_candidates(
        intents, bm25_idx, kg_idx, claims, tags,
        n=fused_top_n, policy=policy,
    )
    fused = _fuse(raw_scores, n=max(fused_top_n, len(raw_scores)))
    if not fused and (
        policy.allowed_file_fragments
        or policy.rejected_file_fragments
        or policy.required_domains
        or policy.required_terms
    ):
        fallback_policy = RetrievalPolicy(kind=intent_kind)
        raw_scores = _gather_candidates(
            intents, bm25_idx, kg_idx, claims, tags,
            n=fused_top_n, policy=fallback_policy,
        )
        fused = _fuse(raw_scores, n=max(fused_top_n, len(raw_scores)))
    fused = _promote_preferred_files(fused, claims, policy, n=fused_top_n)
    fused = _diversify_fused(fused, claims, n=fused_top_n)
    fused = _promote_bm25_anchors(
        fused, claims, bm25_idx, intents, policy, n=fused_top_n,
    )
    candidates = [
        selector_mod.Candidate(
            claim=claims[cid],
            tags=tags.get(cid, ClaimTags(claim_id=cid)),
            fused_score=score,
            meta=meta,
        )
        for cid, score, meta in fused
        if cid in claims
    ]

    if use_selector:
        hits = await selector_mod.select(
            chart, intents, user_message, candidates, k=final_k,
            policy_hint=policy.selector_hint,
        )
        hits = _ensure_preferred_hits(hits, candidates, policy, k=final_k)
    else:
        hits = [
            RetrievalHit(claim=c.claim, tags=c.tags, score=c.fused_score)
            for c in candidates[:final_k]
        ]

    return [_v1_shape(h) for h in hits]


async def retrieve_for_chart_compound(
    chart: dict[str, Any],
    kinds: list[str] | tuple[str, ...],
    user_message: str | None = None,
    *,
    retrieval_focus: list[str] | tuple[str, ...] | None = None,
    index_root: Path | None = None,
    final_k: int = DEFAULT_FINAL_K,
    per_kind_n: int = 20,
    use_selector: bool = True,
) -> list[V1Hit]:
    """Multi-policy retrieval driven by router's primary + secondary intents.

    Why this exists: a single router intent collapses cross-axis questions
    ("讲一下整体" wants meta + personality) into one narrow policy and
    starves the LLM of relevant 古籍. With ``kinds=[primary, *secondary]``
    we let each policy gather its own candidates, union the pools (dedup
    by claim_id, max score), then run ONE selector pass over the merged
    set with combined intents. Selector decides the final mix based on
    the user message + chart, so noisy candidates from a partially
    relevant kind get filtered naturally.

    Cost: BM25 + KG runs N times (cheap, sub-50ms each) but selector
    still runs once. For ``len(kinds) == 1`` this delegates to
    :func:`retrieve_for_chart` and adds zero overhead — chat path can
    call compound unconditionally.
    """
    # 单 kind 直接退化到原 retrieve_for_chart, 语义等价、无开销
    if not kinds:
        return []
    deduped_kinds: list[str] = []
    seen: set[str] = set()
    for k in kinds:
        normalized = k[len("section:"):] if k.startswith("section:") else k
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped_kinds.append(normalized)
    if len(deduped_kinds) == 1:
        return await retrieve_for_chart(
            chart, deduped_kinds[0], user_message,
            retrieval_focus=retrieval_focus, index_root=index_root,
            final_k=final_k, use_selector=use_selector,
        )

    claims, tags, bm25_idx, kg_idx = _bundle(
        str((index_root or _default_index_root()).resolve())
    )
    if not claims:
        logger.warning("retrieval2 index empty — returning []")
        return []

    # 收集所有 kind 的 intent 列表 (合并后给 selector 看完整意图全貌)
    all_intents: list[QueryIntent] = list(_planner_focus_intents(retrieval_focus))
    intents_seen_keys: set[tuple[str, str]] = set()
    for k in deduped_kinds:
        kind_intents = bazi_chart_to_intents(chart, k, user_message)
        for it in kind_intents:
            key = (it.kind, it.text)
            if key not in intents_seen_keys:
                intents_seen_keys.add(key)
                all_intents.append(it)
    if not all_intents:
        return []

    # 每个 kind 跑自己的 policy 拿到 per_kind_n 个候选; 合并去重保留 max score
    # 注意:_fuse 内部 normalize 让每 kind 池的 top 1 都是 1.0 — 不同 kind
    # 之间分数本来不可比。这里取 max 等价于"任一 kind 认为是 top 1 的就保留",
    # 跨 kind 共同看好的得叠加 boost (kind_count_boost) 让交集排前。
    merged: dict[str, tuple[float, dict[str, float], set[str]]] = {}
    policies: list[tuple[str, RetrievalPolicy]] = []
    for k in deduped_kinds:
        policy = build_policy(chart, k, user_message)
        policies.append((k, policy))
        # 每个 policy 用全量 intents (不只是该 kind 的) -- 让其它 kind
        # 的 intent 也通过该 policy 评分; 跨 kind 信号叠加更充分
        raw = _gather_candidates(
            all_intents, bm25_idx, kg_idx, claims, tags,
            n=per_kind_n, policy=policy,
        )
        kind_fused = _fuse(raw, n=per_kind_n)
        kind_fused = _promote_preferred_files(kind_fused, claims, policy, n=per_kind_n)
        kind_fused = _diversify_fused(kind_fused, claims, n=per_kind_n)
        kind_fused = _promote_bm25_anchors(
            kind_fused, claims, bm25_idx, all_intents, policy, n=per_kind_n,
        )
        for cid, score, meta in kind_fused:
            prev = merged.get(cid)
            if prev is None:
                merged[cid] = (score, dict(meta), {k})
            else:
                prev_score, prev_meta, prev_kinds = prev
                prev_kinds.add(k)
                # 取 max score (不累加,跨 kind 分数不可比)
                if score > prev_score:
                    new_meta = dict(prev_meta)
                    new_meta.update(meta)
                    merged[cid] = (score, new_meta, prev_kinds)
                else:
                    merged[cid] = (prev_score, prev_meta, prev_kinds)

    # 跨 kind 都看好的 +0.1 加分, 让交集排前面
    fused_list = []
    for cid, (score, meta, from_kinds) in merged.items():
        final_score = score + 0.1 * (len(from_kinds) - 1)
        meta_with_kinds = dict(meta)
        meta_with_kinds["from_kinds"] = sorted(from_kinds)
        fused_list.append((cid, final_score, meta_with_kinds))

    fused_merged = sorted(fused_list, key=lambda x: x[1], reverse=True)
    pool_size = max(DEFAULT_FUSED_TOP_N, per_kind_n)
    fused_merged = fused_merged[:pool_size]

    candidates = [
        selector_mod.Candidate(
            claim=claims[cid],
            tags=tags.get(cid, ClaimTags(claim_id=cid)),
            fused_score=score,
            meta=meta,
        )
        for cid, score, meta in fused_merged
        if cid in claims
    ]

    if use_selector:
        primary_policy = policies[0][1] if policies else RetrievalPolicy(kind="other")
        # 合并 selector_hint: primary 的 hint + 简短提示有 secondary
        joined_hint = primary_policy.selector_hint
        if len(deduped_kinds) > 1:
            others = "、".join(deduped_kinds[1:])
            joined_hint = (
                f"{joined_hint} 注意:本次同时检索了 [{others}] 的辅助证据,"
                f"主轴是 {deduped_kinds[0]};按用户问题在两类材料之间挑相关的,"
                f"不要因为 {others} 类材料分高就压过 {deduped_kinds[0]} 主题。"
            ).strip()
        hits = await selector_mod.select(
            chart, all_intents, user_message, candidates, k=final_k,
            policy_hint=joined_hint,
        )
        # primary policy 的 preferred_hits 兜底机制保留
        hits = _ensure_preferred_hits(hits, candidates, primary_policy, k=final_k)
    else:
        hits = [
            RetrievalHit(claim=c.claim, tags=c.tags, score=c.fused_score)
            for c in candidates[:final_k]
        ]

    return [_v1_shape(h) for h in hits]


__all__ = ["V1Hit", "retrieve_for_chart", "retrieve_for_chart_compound", "reset_cache"]
