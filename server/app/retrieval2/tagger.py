"""LLM tagger — runs once offline.

Reads ClaimUnit, returns ClaimTags. Uses the project's existing DeepSeek
chat client (no extra dependency). Prompt + parser are versioned together
via :data:`TAGGER_PROMPT_VERSION` (in ``types.py``).

Tagger output is **strictly gated against the controlled vocabulary in
:data:`VOCAB`** — any term the model invents is silently dropped at parse
time. So adding a new vocabulary term requires:

  1. add it to :data:`VOCAB`
  2. bump :data:`TAGGER_PROMPT_VERSION` in ``types.py``
  3. re-run the indexer

The tagger is async + concurrency-safe (no shared mutable state).

Multi-key client pool (2026-05-08): when ``LLM_API_KEYS_EXTRA`` is set,
the tagger creates one AsyncOpenAI client per key (primary + extras) and
round-robins per call. Since each key is a separate upstream account
quota, this lets us bump effective concurrency without tripping the
single-account RemoteProtocolError ceiling.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from .types import ClaimTags, ClaimUnit, TAGGER_PROMPT_VERSION

logger = logging.getLogger(__name__)

# Controlled vocabulary the tagger is allowed to emit.
VOCAB: dict[str, list[str]] = {
    "shishen": [
        "比肩", "劫财", "正印", "偏印",
        "正官", "七杀", "正财", "偏财",
        "食神", "伤官", "建禄", "阳刃",
    ],
    "yongshen_method": ["扶抑", "调候", "通关", "病药", "格局", "专旺"],
    "day_strength": ["身强", "身旺", "身弱", "身轻", "中和", "极弱", "极强", "从格"],
    "domain": [
        "格局成败", "用神取舍", "用神变化", "六亲", "性情", "调候",
        "财官", "疾病", "行运", "神煞", "外貌", "女命", "时上",
    ],
    "season": ["春", "夏", "秋", "冬", "四季"],
    "day_gan": list("甲乙丙丁戊己庚辛壬癸"),
    "month_zhi": list("子丑寅卯辰巳午未申酉戌亥"),
    "geju": [
        "七杀格", "正官格", "正印格", "偏印格", "印绶格",
        "正财格", "偏财格", "财格", "食神格", "伤官格",
        "建禄格", "月劫格", "阳刃格",
        "化气格", "从财格", "从杀格", "从儿格", "从势格",
        "曲直格", "炎上格", "稼穑格", "从革格", "润下格",
        "飞天禄马", "倒冲", "井栏叉", "六阴朝阳", "六乙鼠贵",
        "朝阳格", "金神", "魁罡", "日刃", "日德", "日贵",
    ],
    "kind": [
        "principle",  # 抽象原则:"先观月令"
        "rule",       # 带条件规则:"正官格忌伤官刑冲" (与 principle 同权)
        "case",       # 具体命例:"如甲日某月某时…"
        "formula",    # 诀文/口诀体:"甲日X月為偏官" (与 heuristic 同权)
        "judgement",  # 绝对凶吉断语:"必贫必夭克妻刑子" — 排序时降权
        "shensha",    # 神煞类:"桃花/驿马/孤辰寡宿" — 排序时降权
        "heuristic",  # 经验法则
        "meta",       # 篇首释例 / 表格行
        "unclear",
    ],
}


def _vocab_block() -> str:
    return "\n".join(f"  {k}: [{', '.join(v)}]" for k, v in VOCAB.items())


SYSTEM_PROMPT = f"""你是八字古籍的结构化标注器。读一条 claim，按下表输出标签。
只用受控词表内的值；如果一段 claim 不属于任何受控值，对应字段留空数组。

受控词表：
{_vocab_block()}

字段说明：
- shishen: claim 主要讨论的十神（多选）。
- yongshen_method: 涉及的用神方法。
- day_strength: 适用的日主强弱情境（"杀重身轻"应拆为 day_strength=身轻 + shishen=七杀）。
- domain: 落在哪个生活/命理域。
- season / day_gan / month_zhi: 仅在 claim 明确专属时填，通则留空。
- geju: 提到的具体格局名。
- authority: 0..1。1=主流共识断语；0.5=普通论述；<0.3=偏门口诀。
- refined_kind: 选最贴近的一项。优先级判断:
    * judgement = 绝对凶吉断语("必贫/必夭/克妻/刑子/为祸百端"等);若同段含制化救应("得印化煞/见食制杀/反成贵格")则不选 judgement,改选 principle。
    * shensha = 内容主体在罗列神煞名(桃花/驿马/孤辰/寡宿/空亡/羊刃...),且没有讨论格局/月令/用神/制化结构;若神煞与结构论述混合,选 principle。
    * case = 具体命例(以"如X日"/"某甲X月"开头,或大量干支链)。
    * formula = 短小诀文,典型如"甲日X月為偏官""时上偏财不用多"等口诀体,字数密度高。
    * rule = 带明确触发条件的格局规则,与 principle 几乎同权,只在条件极清晰时才选。
    * principle = 抽象命题/通则,默认选项。
    * heuristic = 长度极短(<18 字)又非诀文的经验法则。
    * meta = 篇首释例 / 表格行 / 编者按。
- confidence: 你这次标注的置信度 0..1。

只输出 JSON。不要解释，不要 fence。"""

_USER_TEMPLATE = """书：{book}
章节：{chapter_title}
小节：{section}
claim_id：{claim_id}
claim 文本：
{text}"""


def build_messages(claim: ClaimUnit) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _USER_TEMPLATE.format(
            book=claim.book, chapter_title=claim.chapter_title,
            section=claim.section or "—", claim_id=claim.id, text=claim.text,
        )},
    ]


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


def _strip_fence(text: str) -> str:
    s = (text or "").strip()
    m = _FENCE_RE.search(s)
    return (m.group(1) if m else s).strip()


def _filter_vocab(values: Any, allowed: list[str]) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return ()
    allowed_set = set(allowed)
    out: list[str] = []
    for v in values:
        s = str(v or "").strip()
        if s in allowed_set and s not in out:
            out.append(s)
    return tuple(out)


def parse_response(text: str, claim_id: str) -> dict[str, Any]:
    try:
        data = json.loads(_strip_fence(text))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, Any] = {"claim_id": claim_id}
    for key in ("shishen", "yongshen_method", "day_strength", "domain",
                "season", "day_gan", "month_zhi", "geju"):
        out[key] = _filter_vocab(data.get(key), VOCAB[key])
    refined = str(data.get("refined_kind") or "").strip()
    out["refined_kind"] = refined if refined in set(VOCAB["kind"]) else "principle"
    try:
        out["authority"] = float(data.get("authority", 0.5))
    except (TypeError, ValueError):
        out["authority"] = 0.5
    try:
        out["tagger_confidence"] = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        out["tagger_confidence"] = 0.0
    return out


# Multi-key client pool. Lazy-built on first use so importing this module
# in test environments without LLM stack stays cheap.
_TAGGER_CLIENTS: list[Any] | None = None
_TAGGER_NEXT_IDX: int = 0
_TAGGER_LOCK = asyncio.Lock()


def _build_tagger_clients() -> list[Any]:
    """Return a list of AsyncOpenAI clients, one per API key.

    Reads ``settings.llm_api_key`` (always) plus ``settings.llm_api_keys_extra``
    (comma-separated) for offline batch tagging. When extras are absent
    the list has length 1 and the tagger falls back to the same single-key
    behaviour as before.
    """
    from openai import AsyncOpenAI
    from app.core.config import settings

    keys: list[str] = []
    if settings.llm_api_key:
        keys.append(settings.llm_api_key)
    extra = (settings.llm_api_keys_extra or "").strip()
    if extra:
        for k in extra.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
    if not keys:
        keys = ["dummy-for-test"]

    return [
        AsyncOpenAI(
            api_key=k, base_url=settings.llm_base_url,
            max_retries=0, timeout=180.0,
            default_headers={"api-key": k},
        )
        for k in keys
    ]


async def _next_client() -> Any:
    """Atomic round-robin pick of the next client from the pool."""
    global _TAGGER_CLIENTS, _TAGGER_NEXT_IDX
    async with _TAGGER_LOCK:
        if _TAGGER_CLIENTS is None:
            _TAGGER_CLIENTS = _build_tagger_clients()
            logger.info("tagger client pool: %d key(s)", len(_TAGGER_CLIENTS))
        client = _TAGGER_CLIENTS[_TAGGER_NEXT_IDX]
        _TAGGER_NEXT_IDX = (_TAGGER_NEXT_IDX + 1) % len(_TAGGER_CLIENTS)
        return client


def reset_tagger_pool() -> None:
    """Test hook — drop cached client pool so subsequent calls re-read settings."""
    global _TAGGER_CLIENTS, _TAGGER_NEXT_IDX
    _TAGGER_CLIENTS = None
    _TAGGER_NEXT_IDX = 0


async def _call_pro_with_thinking(
    client: Any,
    messages: list[dict],
    *,
    timeout_seconds: float,
) -> tuple[str, str]:
    """One LLM call: pro model + thinking on. Returns (text, model_used)."""
    from app.core.config import settings

    model = settings.llm_model  # mimo-v2.5-pro
    response = await asyncio.wait_for(
        client.chat.completions.create(
            model=model,
            messages=messages,
            stream=False,
            temperature=0.0,
            max_tokens=2400,
            extra_body={"thinking": {"type": settings.llm_thinking}},
        ),
        timeout=timeout_seconds,
    )
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise RuntimeError(f"{model} returned no choices")
    msg = getattr(choices[0], "message", None)
    text = str(getattr(msg, "content", None) or "").strip()
    if not text:
        raise RuntimeError(f"{model} returned empty content")
    return text, model


async def tag_one(claim: ClaimUnit, *, timeout_seconds: float = 180.0,
                  max_retries: int = 3) -> ClaimTags:
    """Tag a single claim. Late-imports the chat client so this module is
    importable in environments without the LLM stack.

    Tagger v2 (2026-05-08):
    * Multi-key pool — round-robins per call when LLM_API_KEYS_EXTRA is set.
      Each key is a separate upstream account, so we can drive concurrency
      higher without saturating any one account's connection budget.
    * pro model (mimo-v2.5-pro) — handles the new judgement / shensha
      discrimination better; tagging is one-shot offline so the
      cost-per-quality trade-off skews toward quality.
    * thinking enabled — helps with "is this a structural rule with
      conditions or a fatalistic断语?" judgements that the new
      vocabulary requires.
    * max_tokens=2400 — thinking responses include reasoning tokens that
      count against the cap.
    * timeout=180s — pro+thinking on long claims can hit 60-90s; +safety.
    * max_retries=3 with exponential backoff — handles transient
      RemoteProtocolError disconnects from the upstream MiFE proxy."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        client = await _next_client()
        try:
            text, model = await _call_pro_with_thinking(
                client, build_messages(claim), timeout_seconds=timeout_seconds,
            )
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= max_retries:
                return ClaimTags(
                    claim_id=claim.id,
                    tagger_version=TAGGER_PROMPT_VERSION,
                    tagger_model="(error)",
                    tagger_confidence=0.0,
                )
            # exponential backoff: 0.5s, 1.5s, 4.5s
            await asyncio.sleep(0.5 * (3 ** attempt))
    parsed = parse_response(text, claim.id)
    return ClaimTags(
        claim_id=claim.id,
        shishen=parsed.get("shishen", ()),
        yongshen_method=parsed.get("yongshen_method", ()),
        day_strength=parsed.get("day_strength", ()),
        domain=parsed.get("domain", ()),
        season=parsed.get("season", ()),
        day_gan=parsed.get("day_gan", ()),
        month_zhi=parsed.get("month_zhi", ()),
        geju=parsed.get("geju", ()),
        refined_kind=parsed.get("refined_kind", claim.kind),
        authority=parsed.get("authority", 0.5),
        tagger_version=TAGGER_PROMPT_VERSION,
        tagger_model=model or "deepseek",
        tagger_confidence=parsed.get("tagger_confidence", 0.0),
    )


async def tag_all(
    claims: list[ClaimUnit], *, max_concurrency: int = 32,
    progress_callback: Any = None,
) -> list[ClaimTags]:
    """Tag a list of claims concurrently. Returns in the same order as input.

    ``progress_callback(idx, tag)`` — optional. Called on each completed
    tag (in completion order, not input order) so callers can checkpoint
    partial results to disk. Order-stable return is preserved by sorting
    after gather."""
    sem = asyncio.Semaphore(max_concurrency)

    async def _one(c: ClaimUnit, idx: int) -> tuple[int, ClaimTags]:
        async with sem:
            tag = await tag_one(c)
            if progress_callback is not None:
                try:
                    progress_callback(idx, tag)
                except Exception:  # noqa: BLE001 - callback is best-effort
                    pass
            return idx, tag

    results = await asyncio.gather(*(_one(c, i) for i, c in enumerate(claims)))
    results.sort(key=lambda x: x[0])
    return [t for _, t in results]


__all__ = [
    "VOCAB",
    "SYSTEM_PROMPT",
    "build_messages",
    "parse_response",
    "tag_one",
    "tag_all",
]
