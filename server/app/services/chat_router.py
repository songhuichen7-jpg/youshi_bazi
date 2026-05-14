"""Stage 1 router: LLM-first classifier with keyword fallback on outage."""
from __future__ import annotations

import time
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import chat_once_with_fallback
from app.llm.logs import insert_llm_usage_log
from app.models.user import User
from app.prompts.router import (
    build_messages,
    classify_by_keywords,
    normalize_route_plan,
    parse_router_json,
)
from app.services.exceptions import UpstreamLLMError


async def classify(
    *, db: AsyncSession, user: User, chart_id: UUID,
    message: str, history: list[dict],
) -> dict:
    """Returns {intent, reason, source}. Logs llm_usage_logs row for each attempt."""

    t_start = time.monotonic()
    model_used: str | None = None
    err: UpstreamLLMError | None = None
    parsed = normalize_route_plan({"intent": "other", "reason": "router_error"})

    try:
        text, model_used = await chat_once_with_fallback(
            messages=build_messages(history=history, user_message=message),
            tier="fast", temperature=0, max_tokens=1600,
            disable_thinking=True,
        )
        parsed = parse_router_json(text)
    except UpstreamLLMError as e:
        err = e

    duration_ms = int((time.monotonic() - t_start) * 1000)
    await insert_llm_usage_log(
        db, user_id=user.id, chart_id=chart_id,
        endpoint="chat:router", model=model_used,
        prompt_tokens=None,
        completion_tokens=None,
        duration_ms=duration_ms,
        error=(f"{err.code}: {err.message}" if err else None),
    )

    if err:
        keyword_fallback = classify_by_keywords(message)
        if keyword_fallback:
            keyword_fallback["source"] = "keyword_fallback"
            keyword_fallback["reason"] = f"router_error;{keyword_fallback['reason']}"
            return keyword_fallback
        parsed["source"] = "llm_error"
    else:
        parsed["source"] = "llm"

    if "artifact" not in parsed:
        parsed["artifact"] = {"enabled": False, "kind": None, "reason": ""}
    return parsed
