"""DeepSeek-as-selector — picks the best K claims out of ~30 candidates.

This is the **key new component** that replaces the cross-encoder reranker.
For our deployment (2GB RAM domestic-API server), this is the right tradeoff:

* No model weights, no torch. Zero deployment footprint.
* Uses the existing DeepSeek client; no new API integration.
* ~500ms-1s latency per call — acceptable since baseline chat is 10-20s.
* Sees full chart context + user question, not just (query, doc) pairs.
  This actually beats cross-encoder rerankers on highly contextual tasks.

Failure modes are explicit and graceful:
* LLM call timeout / error → fall back to top-N by candidate score.
* Bad JSON → fall back to top-N by candidate score.
* IDs the LLM made up → silently dropped.
* Fewer confident picks → return fewer hits; precision beats padding.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Sequence

from .types import ClaimUnit, QueryIntent, RetrievalHit, ClaimTags

logger = logging.getLogger(__name__)

DEFAULT_K = 6
DEFAULT_MAX_CANDIDATES = 30
DEFAULT_TIMEOUT_SECONDS = 20.0


@dataclass(slots=True)
class Candidate:
    claim: ClaimUnit
    tags: ClaimTags
    fused_score: float
    meta: dict[str, float] | None = None


_SYSTEM = """你是八字检索结果的精排器。给你一个命盘+用户问题+一批候选古籍 claim，
你要挑出最直接对题、最有信息密度的几条，并标注每条对应哪个分论点。

打分原则：
- 直接答用户问题的（一句道破型）排首位
- 普遍命题 > 具体案例（除非用户明确想看案例）
- 同一观点重复出现，只挑信号最强、表述最精的一条
- 偏门神煞 / 杂格权重低；但訣文/口诀体（如三命通会"甲日X月為偏官..."）信号密度高，不要因为短就丢
- 「必贫必夭」「克妻刑子」类绝对凶吉断语不要引用，除非同段紧跟制化救应（"得印化煞""见食制杀"）
- 与命盘强弱、格局、月令、用神不对应的，直接淘汰
- 同一 chapter_file + section（古籍同一章节）最多挑 1 条；优先跨古籍、跨章节铺开
- 命盘块附带的「事实表」是后端规则计算的，十神身份、透藏状态、干合关系全部以事实表为准；不要凭记忆把伤官当食神、把藏支说成透干。判断候选与命盘是否对应时以事实表为唯一依据

每条 pick 必须包含 ``supports`` 字段，从「系统识别的检索意图」里挑一个 kind
作为该证据的支持目标（例：``tiaohou`` / ``main_geju`` / ``yongshen.X`` /
``combo.day_hour`` / ``shen_sha.*`` / ``xingyun.*`` / ``liu_qin.specific`` /
``user_msg``）。如果同一条证据可以同时支持多个意图，挑信号最强的那个；
若都搭不上，留空字符串 ``""``。

只输出 JSON：
{"picks":[{"id":"<claim_id>","reason":"<10-20字>","supports":"<intent.kind 或 \\"\\">"}]}

picks 数组按相关性从高到低排列。最多给 N 条；宁缺毋滥。
不要解释，不要 ```fence。"""


def _format_chart(chart: dict) -> str:
    p = chart.get("PAIPAN") or chart
    sizhu = p.get("sizhu") or {}
    parts = [
        f"四柱: 年{sizhu.get('year','')} 月{sizhu.get('month','')} 日{sizhu.get('day','')} 时{sizhu.get('hour','')}",
        f"日主: {p.get('rizhu','')}",
        f"格局: {p.get('geju','')}",
        f"强弱: {p.get('dayStrength','')}",
        f"用神: {p.get('yongshen','')}",
    ]
    head = "  ".join(s for s in parts if s.split(": ", 1)[-1])
    # Pin authoritative ten-god / 透藏 / 干合 facts so the selector doesn't
    # mislabel candidates by recall (same gap polisher had — when scoring
    # "this claim mentions 食神制杀" relevance, the model needs to know whether
    # the chart's 用神 is actually 食神 or 伤官).
    from .chart_facts import ten_god_facts
    facts = ten_god_facts(chart)
    if facts:
        return head + "\n  事实表（必须严格遵循）：\n  " + "\n  ".join(facts)
    return head


def _format_intents(intents: Sequence[QueryIntent]) -> str:
    lines: list[str] = []
    for it in intents:
        if it.kind == "user_msg":
            continue
        if it.text:
            lines.append(f"  · {it.kind}: {it.text}")
    return "\n".join(lines)


def _format_tags(tags: ClaimTags) -> str:
    parts: list[str] = []
    for label, values in (
        ("domain", tags.domain),
        ("shishen", tags.shishen),
        ("method", tags.yongshen_method),
        ("strength", tags.day_strength),
        ("day_gan", tags.day_gan),
        ("month_zhi", tags.month_zhi),
        ("geju", tags.geju),
    ):
        if values:
            parts.append(f"{label}={','.join(values)}")
    return "；".join(parts) or "无结构标签"


def _format_candidates(candidates: Sequence[Candidate]) -> str:
    lines: list[str] = []
    for c in candidates:
        text = c.claim.text.replace("\n", " ").strip()
        if len(text) > 220:
            text = text[:220] + "…"
        src = " · ".join(p for p in (c.claim.chapter_file, c.claim.chapter_title, c.claim.section) if p)
        lines.append(
            f"[{c.claim.id}] {src}\n"
            f"  tags: {_format_tags(c.tags)}\n"
            f"  text: {text}"
        )
    return "\n".join(lines)


def _user_message(
    chart: dict,
    intents: Sequence[QueryIntent],
    user_msg: str | None,
    candidates: Sequence[Candidate],
    k: int,
    policy_hint: str = "",
) -> str:
    user_q = user_msg or "（用户未直接提问；按命盘整体特征做检索）"
    hint = policy_hint or "按用户问题、命盘结构、候选标签与原文直接相关性筛选。"
    return (
        f"【命盘】\n  {_format_chart(chart)}\n\n"
        f"【用户问题】\n  {user_q}\n\n"
        f"【系统识别的检索意图】\n{_format_intents(intents) or '  · meta'}\n\n"
        f"【本轮精排规则】\n  {hint}\n\n"
        f"【候选 claim（共 {len(candidates)} 条）】\n{_format_candidates(candidates)}\n\n"
        f"请从中精选最多 {k} 条，宁缺毋滥；不够对题的候选不要为了凑数输出。输出 JSON。"
    )


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


def _strip_fence(text: str) -> str:
    s = (text or "").strip()
    m = _FENCE_RE.search(s)
    return (m.group(1) if m else s).strip()


def parse_picks(text: str, valid_ids: set[str]) -> list[tuple[str, str, str]]:
    """Parse selector output. Returns ``[(claim_id, reason, supports), ...]``
    in order. Drops ids not in ``valid_ids``. ``supports`` is "" when the
    selector didn't tag this pick."""
    try:
        data = json.loads(_strip_fence(text))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    picks = data.get("picks") or []
    if not isinstance(picks, list):
        return []
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for item in picks:
        if isinstance(item, dict):
            cid = str(item.get("id") or "").strip()
            reason = str(item.get("reason") or "").strip()[:80]
            supports = str(item.get("supports") or "").strip()[:48]
        elif isinstance(item, str):
            cid, reason, supports = item.strip(), "", ""
        else:
            continue
        if cid and cid in valid_ids and cid not in seen:
            out.append((cid, reason, supports))
            seen.add(cid)
    return out


def _topup(picks: list[tuple[str, str, str]], candidates: Sequence[Candidate],
           k: int) -> list[tuple[str, str, str, float]]:
    """Append fallback candidates by fused_score until we have k items."""
    seen = {cid for cid, _, _ in picks}
    score_map = {c.claim.id: c.fused_score for c in candidates}
    out: list[tuple[str, str, str, float]] = [
        (cid, reason, supports, score_map.get(cid, 0.0))
        for cid, reason, supports in picks
    ]
    for c in sorted(candidates, key=lambda x: x.fused_score, reverse=True):
        if len(out) >= k:
            break
        if c.claim.id in seen:
            continue
        out.append((c.claim.id, "", "", c.fused_score))
        seen.add(c.claim.id)
    return out


async def _call_deepseek(messages: list[dict], *, timeout: float) -> str:
    from app.llm.client import chat_once_with_fallback

    text, _ = await asyncio.wait_for(
        chat_once_with_fallback(
            messages=messages,
            tier="fast", temperature=0.0, max_tokens=1200,
            disable_thinking=True,
        ),
        timeout=timeout,
    )
    return text


async def select(
    chart: dict,
    intents: Sequence[QueryIntent],
    user_msg: str | None,
    candidates: Sequence[Candidate],
    *,
    k: int = DEFAULT_K,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    policy_hint: str = "",
) -> list[RetrievalHit]:
    """Pick best k claims from candidates using DeepSeek.

    Returns up to k :class:`RetrievalHit`. On any LLM-call failure, falls
    back to top-k by ``fused_score`` (no exception thrown).
    """
    if not candidates:
        return []
    # Trim candidates to manage prompt size and cost.
    pool = list(candidates)[:max_candidates]
    valid_ids = {c.claim.id for c in pool}

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _user_message(
            chart, intents, user_msg, pool, k, policy_hint,
        )},
    ]
    try:
        text = await _call_deepseek(messages, timeout=timeout_seconds)
        picks = parse_picks(text, valid_ids)
    except Exception as exc:  # noqa: BLE001
        logger.warning("selector LLM call failed: %s — falling back to fused_score", exc)
        picks = []

    if picks:
        score_map = {c.claim.id: c.fused_score for c in pool}
        final = [
            (cid, reason, supports, score_map.get(cid, 0.0))
            for cid, reason, supports in picks[:k]
        ]
    else:
        final = _topup(picks, pool, k)
    by_id = {c.claim.id: c for c in pool}
    out: list[RetrievalHit] = []
    for cid, reason, supports, score in final[:k]:
        c = by_id.get(cid)
        if c is None:
            continue
        out.append(RetrievalHit(
            claim=c.claim, tags=c.tags,
            score=score if score else 0.5,
            reason=reason,
            claim_supported=supports,
        ))
    return out


__all__ = ["Candidate", "select", "parse_picks", "DEFAULT_K"]
