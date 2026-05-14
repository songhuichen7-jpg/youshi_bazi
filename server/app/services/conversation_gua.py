"""Gua SSE generator. NOTE: spec §6."""
from __future__ import annotations

import time
from collections.abc import AsyncIterator
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.llm.client import chat_stream_with_fallback
from app.llm.events import sse_pack
from app.llm.logs import insert_llm_usage_log
from app.models.user import User
from app.prompts.gua import build_messages as build_gua_messages
from app.services import message as msg_svc
from app.services.exceptions import UpstreamLLMError
from app.services.gua_cast import cast_gua
from app.services.quota import QuotaTicket


def _derive_birth_context(paipan: dict) -> dict:
    """Pick rizhu + current dayun gz + current year gz from flat chart.paipan."""
    paipan = paipan or {}
    rizhu = paipan.get("rizhu")
    today_year_gz = paipan.get("todayYearGz")
    today_year_str = (paipan.get("todayYmd") or "")[:4]
    today_year = int(today_year_str) if today_year_str.isdigit() else None

    current_dayun_gz = None
    if today_year is not None:
        raw_dayun = paipan.get("dayun") or {}
        if isinstance(raw_dayun, dict):
            dayun_list = raw_dayun.get("list") or []
        else:
            dayun_list = list(raw_dayun)
        for step in dayun_list:
            try:
                sy, ey = int(step.get("startYear")), int(step.get("endYear"))
            except (TypeError, ValueError):
                continue
            if sy <= today_year <= ey:
                # dayun entries use 'ganZhi' or 'ganzhi' (varies)
                current_dayun_gz = step.get("ganZhi") or step.get("ganzhi") or step.get("gz")
                break

    return {
        "rizhu": rizhu,
        "currentDayun": current_dayun_gz,
        "currentYear": today_year_gz,
    }


async def stream_gua(
    *, db: AsyncSession, user: User, conversation_id: UUID,
    chart, question: str, ticket: QuotaTicket,
) -> AsyncIterator[bytes]:
    """Cast hexagram → emit gua → stream LLM → consume cta → INSERT gua msg.

    NOTE: spec §6.1.
    """
    # cast_gua requires local Chinese calendar time per its docstring contract.
    gua = cast_gua(datetime.now(tz=ZoneInfo("Asia/Shanghai")))
    yield sse_pack({"type": "gua", "data": gua})

    birth_ctx = _derive_birth_context(chart.paipan)
    messages_llm = build_gua_messages(question=question, gua=gua, birth_context=birth_ctx)

    accumulator = ""
    model_used: str | None = None
    prompt_tok = completion_tok = total_tok = 0
    t_start = time.monotonic()
    err: UpstreamLLMError | None = None

    try:
        async for ev in chat_stream_with_fallback(
            messages=messages_llm, tier="primary",
            temperature=0.7, max_tokens=2000,
            first_delta_timeout_ms=settings.llm_stream_first_delta_ms,
        ):
            t = ev["type"]
            if t == "model":
                model_used = ev["modelUsed"]
                yield sse_pack(ev)
            elif t == "delta":
                accumulator += ev["text"]
                yield sse_pack(ev)
            elif t == "thinking":
                yield sse_pack(ev)  # 透传，不入 accumulator
            elif t == "done":
                prompt_tok = ev.get("prompt_tokens", 0)
                completion_tok = ev.get("completion_tokens", 0)
                total_tok = ev.get("tokens_used", 0)
    except UpstreamLLMError as e:
        err = e
        yield sse_pack({"type": "error", "code": e.code, "message": e.message})

    duration_ms = int((time.monotonic() - t_start) * 1000)

    if err is not None:
        await insert_llm_usage_log(
            db, user_id=user.id, chart_id=chart.id,
            endpoint="gua", model=model_used,
            prompt_tokens=None, completion_tokens=None,
            duration_ms=duration_ms, error=f"{err.code}: {err.message}",
        )
        return

    try:
        await ticket.commit()
    except Exception as e:  # noqa: BLE001 — quota race or other commit failure
        yield sse_pack({"type": "error", "code": "QUOTA_EXCEEDED", "message": str(e)})
        await insert_llm_usage_log(
            db, user_id=user.id, chart_id=chart.id,
            endpoint="gua", model=model_used,
            prompt_tokens=None, completion_tokens=None,
            duration_ms=duration_ms, error=f"QUOTA_EXCEEDED: {e}",
        )
        return

    # Consume cta if present (atomic with insert below)
    await msg_svc.delete_last_cta(db, conversation_id=conversation_id)
    await msg_svc.insert(
        db, conversation_id=conversation_id, role="gua",
        content=None,
        meta={
            "gua": gua, "question": question,
            "body": accumulator, "model_used": model_used,
        },
    )
    await insert_llm_usage_log(
        db, user_id=user.id, chart_id=chart.id,
        endpoint="gua", model=model_used,
        prompt_tokens=prompt_tok, completion_tokens=completion_tok,
        duration_ms=duration_ms,
    )
    yield sse_pack({"type": "done", "full": accumulator, "tokens_used": total_tok})
