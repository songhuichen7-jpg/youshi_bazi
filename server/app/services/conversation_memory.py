"""Rolling long-term memory for chat conversations."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import chat_once_with_fallback
from app.llm.logs import insert_llm_usage_log
from app.models.conversation import ConversationSummary, Message
from app.models.user import User

_log = logging.getLogger(__name__)

SUMMARY_RECENT_KEEP = 24
SUMMARY_MIN_NEW_MESSAGES = 8
SUMMARY_INPUT_CHAR_LIMIT = 12_000
SUMMARY_MAX_CHARS = 3_200


async def get_summary(db: AsyncSession, *, conversation_id: UUID) -> str | None:
    row = await db.get(ConversationSummary, conversation_id)
    if row is None:
        return None
    text = (row.summary or "").strip()
    return text or None


def _message_older_than(row: Message):
    return or_(
        Message.created_at < row.created_at,
        and_(Message.created_at == row.created_at, Message.id < row.id),
    )


def _message_newer_than(row: Message):
    return or_(
        Message.created_at > row.created_at,
        and_(Message.created_at == row.created_at, Message.id > row.id),
    )


def _message_cost(row: Message) -> int:
    return len(row.role or "") + len(row.content or "")


def _render_dialogue(rows: list[Message]) -> str:
    rendered: list[str] = []
    role_names = {"user": "用户", "assistant": "助手"}
    for row in rows:
        content = " ".join((row.content or "").split())
        if not content:
            continue
        rendered.append(f"{role_names.get(row.role, row.role)}：{content}")
    return "\n".join(rendered)


def _clip_summary(text: str) -> str:
    normalized = text.strip()
    if len(normalized) <= SUMMARY_MAX_CHARS:
        return normalized
    return normalized[:SUMMARY_MAX_CHARS].rstrip() + "…"


def _build_summary_messages(previous_summary: str | None, new_rows: list[Message]) -> list[dict[str, str]]:
    previous = previous_summary.strip() if previous_summary else "（暂无）"
    dialogue = _render_dialogue(new_rows)
    return [
        {
            "role": "system",
            "content": (
                "你在维护一个八字聊天应用的对话长期记忆。"
                "请把旧摘要和新增对话合并成一份简洁、稳定、可继续使用的摘要。"
                "只保留对后续聊天有用的信息：用户关注点、已确认的命盘判断、古籍旁证取向、"
                "用户偏好、未解决问题。不要编造，不要写寒暄，不要保留逐字流水账。"
            ),
        },
        {
            "role": "user",
            "content": (
                "【旧摘要】\n"
                f"{previous}\n\n"
                "【新增对话】\n"
                f"{dialogue}\n\n"
                "请输出更新后的长期记忆，控制在 10-18 条要点内。"
            ),
        },
    ]


async def _eligible_rows(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    summary: ConversationSummary | None,
    recent_keep: int,
) -> list[Message]:
    recent_keep = max(1, recent_keep)
    tail_stmt = (
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.role.in_(["user", "assistant"]),
        )
        .order_by(desc(Message.created_at), desc(Message.id))
        .limit(recent_keep + 1)
    )
    tail = (await db.execute(tail_stmt)).scalars().all()
    if len(tail) <= recent_keep:
        return []

    cutoff = tail[recent_keep - 1]
    stmt = (
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.role.in_(["user", "assistant"]),
            _message_older_than(cutoff),
        )
        .order_by(Message.created_at, Message.id)
    )
    if summary and summary.covered_message_id:
        covered = await db.get(Message, summary.covered_message_id)
        if covered is not None:
            stmt = stmt.where(_message_newer_than(covered))

    rows = (await db.execute(stmt)).scalars().all()
    selected: list[Message] = []
    used = 0
    for row in rows:
        cost = _message_cost(row)
        if selected and used + cost > SUMMARY_INPUT_CHAR_LIMIT:
            break
        selected.append(row)
        used += cost
    return selected


async def maybe_refresh_summary(
    db: AsyncSession,
    *,
    user: User,
    chart: Any,
    conversation_id: UUID,
    recent_keep: int = SUMMARY_RECENT_KEEP,
    min_new_messages: int = SUMMARY_MIN_NEW_MESSAGES,
) -> bool:
    """Summarize older turns not covered by raw recent history.

    Best effort: failures are logged and swallowed so the chat response is not
    affected. Returns True only when the stored summary changed.
    """
    try:
        summary = await db.get(ConversationSummary, conversation_id)
        rows = await _eligible_rows(
            db,
            conversation_id=conversation_id,
            summary=summary,
            recent_keep=recent_keep,
        )
        if len(rows) < max(1, min_new_messages):
            return False

        previous = summary.summary if summary else None
        messages = _build_summary_messages(previous, rows)
        started = time.monotonic()
        content, model_used = await chat_once_with_fallback(
            messages=messages,
            tier="fast",
            temperature=0.2,
            max_tokens=1400,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        new_summary = _clip_summary(content)
        if not new_summary:
            return False

        if summary is None:
            summary = ConversationSummary(
                conversation_id=conversation_id,
                summary=new_summary,
                covered_message_id=rows[-1].id,
                covered_message_count=len(rows),
                updated_at=datetime.now(tz=timezone.utc),
            )
            db.add(summary)
        else:
            summary.summary = new_summary
            summary.covered_message_id = rows[-1].id
            summary.covered_message_count = (summary.covered_message_count or 0) + len(rows)
            summary.updated_at = datetime.now(tz=timezone.utc)
        await db.flush()
        await insert_llm_usage_log(
            db,
            user_id=user.id,
            chart_id=getattr(chart, "id", None),
            endpoint="chat:summary",
            model=model_used,
            prompt_tokens=None,
            completion_tokens=None,
            duration_ms=duration_ms,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        _log.warning("conversation summary refresh failed: %s", exc)
        return False
