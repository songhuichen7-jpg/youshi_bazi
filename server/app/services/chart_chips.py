"""chips SSE generator — FAST_MODEL tier, no cache, no quota, no retrieval."""
from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.llm.client import chat_stream_with_fallback
from app.llm.events import sse_pack
from app.llm.logs import insert_llm_usage_log
from app.models.chart import Chart
from app.models.user import User
from app.prompts.chips import build_messages
from app.services.exceptions import UpstreamLLMError


async def stream_chips(
    db: AsyncSession, user: User, chart: Chart,
    conversation_id: Optional[UUID] = None,
) -> AsyncIterator[bytes]:
    """FAST_MODEL tier. No cache / quota / retrieval. Errors → error event."""
    history: list[dict] = []
    if conversation_id is not None:
        from app.services import message as _msg  # lazy: avoid circular import at module level
        history = await _msg.recent_chat_history(
            db, conversation_id=conversation_id, limit=6,
        )
    messages = build_messages(chart.paipan, history=history)
    accumulated = ""
    model_used: str | None = None
    prompt_tok = completion_tok = total_tok = 0
    t_start = time.monotonic()
    err_code = err_msg = None

    try:
        async for ev in chat_stream_with_fallback(
            messages=messages, tier="fast",
            temperature=0.9, max_tokens=600,
            first_delta_timeout_ms=settings.llm_stream_first_delta_ms,
            disable_thinking=True,
        ):
            if ev["type"] == "model":
                model_used = ev["modelUsed"]
                yield sse_pack(ev)
            elif ev["type"] == "delta":
                accumulated += ev["text"]
                yield sse_pack(ev)
            elif ev["type"] == "done":
                prompt_tok = ev.get("prompt_tokens", 0)
                completion_tok = ev.get("completion_tokens", 0)
                total_tok = ev.get("tokens_used", 0)
                yield sse_pack({
                    "type": "done",
                    "full": accumulated,
                    "tokens_used": total_tok,
                })
    except UpstreamLLMError as e:
        err_code, err_msg = e.code, e.message
        yield sse_pack({"type": "error", "code": e.code, "message": e.message})

    duration_ms = int((time.monotonic() - t_start) * 1000)
    await insert_llm_usage_log(
        db, user_id=user.id, chart_id=chart.id,
        endpoint="chips", model=model_used,
        prompt_tokens=prompt_tok or None,
        completion_tokens=completion_tok or None,
        duration_ms=duration_ms,
        error=(f"{err_code}: {err_msg}" if err_code else None),
    )
