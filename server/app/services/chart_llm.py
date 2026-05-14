"""Cache-aware chart LLM SSE generator + helpers.

Shared by 4 routes: verdicts / sections / dayun_step / liunian.
chips has its own generator (chart_chips.py) because it skips cache/quota.
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.llm.client import chat_stream_with_fallback
from app.llm.events import replay_cached, sse_pack
from app.llm.logs import insert_llm_usage_log
from app.models.chart import ChartCache
from app.models.user import User
from app.retrieval2.service import retrieve_for_chart
from app.services.exceptions import UpstreamLLMError
from app.services.quota import QuotaTicket


async def get_cache_row(
    db: AsyncSession, chart_id: UUID, kind: str, key: str,
) -> ChartCache | None:
    stmt = select(ChartCache).where(
        ChartCache.chart_id == chart_id,
        ChartCache.kind == kind,
        ChartCache.key == key,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def upsert_cache(
    db: AsyncSession, *,
    chart_id: UUID, kind: str, key: str,
    content: str, model_used: str | None, tokens_used: int,
    regen_increment: bool,
) -> None:
    """INSERT ... ON CONFLICT DO UPDATE. regen_count += int(regen_increment).

    Uses pg_insert so that EncryptedText.process_bind_param is applied to
    the 'content' column (raw text() bypasses TypeDecorators).
    """
    from sqlalchemy import func, literal_column
    stmt = pg_insert(ChartCache).values(
        chart_id=chart_id,
        kind=kind,
        key=key,
        content=content,
        model_used=model_used,
        tokens_used=tokens_used,
        generated_at=func.now(),
        regen_count=0,
    ).on_conflict_do_update(
        constraint="uq_chart_cache_slot",
        set_={
            "content": content,
            "model_used": model_used,
            "tokens_used": tokens_used,
            "generated_at": func.now(),
            "regen_count": ChartCache.regen_count + (1 if regen_increment else 0),
        },
    )
    await db.execute(stmt)


async def stream_chart_llm(
    db: AsyncSession, user: User, chart, *,
    kind: Literal["verdicts", "section", "dayun_step", "liunian"],
    key: str,
    force: bool,
    cache_row: ChartCache | None,
    ticket: QuotaTicket | None,
    build_messages: Callable[..., list[dict]],
    retrieval_kind: str,
    temperature: float = 0.7,
    max_tokens: int = 3000,
    tier: Literal["primary", "fast"] = "primary",
) -> AsyncIterator[bytes]:
    """Unified SSE generator. See spec §2.6.

    1. Cache hit + not force → replay_cached (no LLM, no quota)
    2. Else: retrieval → LLM stream → UPSERT cache → log → ticket.commit
    3. LLM error → emit error event, don't write cache, don't commit ticket
    """
    # 1. Cache hit branch
    if cache_row and not force:
        async for raw in replay_cached(cache_row.content, cache_row.model_used):
            yield raw
        return

    # 2. Generate branch
    retrieved = []
    try:
        retrieved = await retrieve_for_chart(chart.paipan, retrieval_kind)
    except Exception:   # noqa: BLE001 — retrieval is best-effort
        retrieved = []
    if retrieved:
        sources = " + ".join(h.get("source", "?") for h in retrieved)
        yield sse_pack({"type": "retrieval", "source": sources})

    messages = build_messages(chart.paipan, retrieved)
    accumulated = ""
    model_used: str | None = None
    prompt_tok = completion_tok = total_tok = 0
    finish_reason: str | None = None
    t_start = time.monotonic()
    err: UpstreamLLMError | None = None

    try:
        async for ev in chat_stream_with_fallback(
            messages=messages, tier=tier,
            temperature=temperature, max_tokens=max_tokens,
            first_delta_timeout_ms=settings.llm_stream_first_delta_ms,
        ):
            if ev["type"] == "model":
                model_used = ev["modelUsed"]
                yield sse_pack(ev)
            elif ev["type"] == "delta":
                accumulated += ev["text"]
                yield sse_pack(ev)
            elif ev["type"] == "done":
                # NOTE: DO NOT yield done here — commit ticket first so race
                # surfaces as `error` instead of `done → error` (Plan 5 cleanup Task 4).
                prompt_tok = ev.get("prompt_tokens", 0)
                completion_tok = ev.get("completion_tokens", 0)
                total_tok = ev.get("tokens_used", 0)
                finish_reason = ev.get("finish_reason")
    except UpstreamLLMError as e:
        err = e
        yield sse_pack({"type": "error", "code": e.code, "message": e.message})

    duration_ms = int((time.monotonic() - t_start) * 1000)

    if err is not None:
        # Log error attempt; don't write cache; don't commit ticket.
        await insert_llm_usage_log(
            db, user_id=user.id, chart_id=chart.id,
            endpoint=kind, model=model_used,
            prompt_tokens=None, completion_tokens=None,
            duration_ms=duration_ms, error=f"{err.code}: {err.message}",
            retrieval_claims=retrieved or None,
        )
        return

    # Truncated path: finish_reason == "length" means max_tokens hit. Treat
    # like an error from the user's perspective —— don't cache (so next view
    # regenerates instead of staying stuck on partial) and don't commit
    # ticket (user shouldn't pay for an incomplete answer). Still emit `done`
    # with finish_reason so the frontend can show a "regenerate" prompt.
    if finish_reason == "length":
        await insert_llm_usage_log(
            db, user_id=user.id, chart_id=chart.id,
            endpoint=kind, model=model_used,
            prompt_tokens=prompt_tok, completion_tokens=completion_tok,
            duration_ms=duration_ms,
            error="TRUNCATED: finish_reason=length",
            retrieval_claims=retrieved or None,
        )
        yield sse_pack({
            "type": "done",
            "full": accumulated,
            "tokens_used": total_tok,
            "finish_reason": finish_reason,
        })
        return

    # Success path: commit-before-done (Plan 5 cleanup Task 4).
    # On race: emit error INSTEAD of done, don't write cache.
    if ticket is not None:
        try:
            await ticket.commit()
        except Exception as e:  # noqa: BLE001 — race: another request pushed us over limit
            yield sse_pack({"type": "error", "code": "QUOTA_EXCEEDED", "message": str(e)})
            await insert_llm_usage_log(
                db, user_id=user.id, chart_id=chart.id,
                endpoint=kind, model=model_used,
                prompt_tokens=None, completion_tokens=None,
                duration_ms=duration_ms, error=f"QUOTA_EXCEEDED: {e}",
            )
            return

    # Commit succeeded (or no ticket) — write cache + log + finally emit done.
    await upsert_cache(
        db,
        chart_id=chart.id, kind=kind, key=key,
        content=accumulated, model_used=model_used, tokens_used=total_tok,
        regen_increment=(cache_row is not None and force),
    )
    await insert_llm_usage_log(
        db, user_id=user.id, chart_id=chart.id,
        endpoint=kind, model=model_used,
        prompt_tokens=prompt_tok, completion_tokens=completion_tok,
        duration_ms=duration_ms, retrieval_claims=retrieved or None,
    )
    yield sse_pack({
        "type": "done",
        "full": accumulated,
        "tokens_used": total_tok,
        "finish_reason": finish_reason,
    })
