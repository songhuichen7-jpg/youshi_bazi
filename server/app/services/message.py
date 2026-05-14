"""Message insert + keyset pagination + helpers used by chat/gua orchestrators."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Message
from app.schemas.message import MessageDetail


CHAT_CONTEXT_MAX_MESSAGES = 60
CHAT_CONTEXT_CHAR_BUDGET = 18_000
CHAT_CONTEXT_ALWAYS_KEEP = 12


async def insert(
    db: AsyncSession, *,
    conversation_id: UUID, role: str,
    content: Optional[str] = None,
    meta: Optional[dict[str, Any]] = None,
) -> Message:
    """INSERT a message row. Caller commits.

    created_at is set from the Python wall-clock (not PostgreSQL's now()) so
    that messages inserted in rapid succession within the same DB transaction
    still have strictly increasing timestamps for reliable ORDER BY.
    """
    m = Message(
        conversation_id=conversation_id,
        role=role, content=content, meta=meta,
        created_at=datetime.now(tz=timezone.utc),
    )
    db.add(m)
    await db.flush()
    await db.refresh(m, ["created_at", "id"])
    return m


def _to_detail(m: Message) -> MessageDetail:
    return MessageDetail(
        id=m.id, role=m.role, content=m.content, meta=m.meta,
        created_at=m.created_at,
    )


async def paginate(
    db: AsyncSession, *,
    conversation_id: UUID,
    before: Optional[UUID],
    limit: int,
) -> dict:
    """Newest-first keyset pagination. NOTE: spec §4.3.

    Returns {"items": [Message...], "next_cursor": UUID|None}.

    next_cursor is the id of the last item in the current page; pass it as
    ``before`` to fetch the next (older) page. None means no more pages.
    """
    if limit < 1 or limit > 100:
        raise ValueError(f"limit must be in [1, 100], got {limit}")

    stmt = select(Message).where(Message.conversation_id == conversation_id)
    if before is not None:
        # Resolve cursor row to (created_at, id) tuple
        cursor_row = (await db.execute(
            select(Message.created_at, Message.id).where(Message.id == before)
        )).one_or_none()
        if cursor_row is None:
            # Cursor refers to a non-existent message — treat as fresh page
            pass
        else:
            c_at, c_id = cursor_row
            stmt = stmt.where(
                (Message.created_at < c_at) |
                ((Message.created_at == c_at) & (Message.id < c_id))
            )

    stmt = stmt.order_by(desc(Message.created_at), desc(Message.id)).limit(limit + 1)
    rows = (await db.execute(stmt)).scalars().all()
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = items[-1].id if has_more and items else None
    return {"items": [_to_detail(m) for m in items], "next_cursor": next_cursor}


async def recent_chat_history(
    db: AsyncSession, *, conversation_id: UUID, limit: int = 8,
) -> list[dict]:
    """Last N user/assistant messages in chronological order, dict-shaped for prompts.

    Used by chat (limit=8), router (limit=4), chips (limit=6).
    """
    stmt = (
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.role.in_(["user", "assistant"]),
        )
        .order_by(desc(Message.created_at), desc(Message.id))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    rows.reverse()  # chronological
    return [{"role": m.role, "content": m.content or ""} for m in rows]


async def latest_assistant_intent(
    db: AsyncSession, *, conversation_id: UUID,
) -> str | None:
    """Return the intent stored on the most recent assistant message in this
    conversation, or None if there isn't one (or it has no intent meta).

    Kept for legacy admin/debug inspection; the chat router no longer inherits
    this value for short follow-up messages."""
    stmt = (
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.role == "assistant",
        )
        .order_by(desc(Message.created_at), desc(Message.id))
        .limit(1)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if not row or not row.meta:
        return None
    intent = row.meta.get("intent") if isinstance(row.meta, dict) else None
    return intent if isinstance(intent, str) and intent else None


async def delete_latest_assistant(
    db: AsyncSession, *, conversation_id: UUID,
) -> bool:
    """Delete the most recent assistant message in the conversation, if any.

    Used by chat regeneration ("重新回答"): the frontend already reset the
    last assistant slot to an empty placeholder, so the DB must drop the
    stale answer too — otherwise refreshing history shows the old answer
    duplicated alongside the new one. The conv-level distributed lock in
    stream_message guarantees there's no concurrent stream writing to this
    same conversation, so deleting unconditionally is safe.

    Returns True if a row was deleted.
    """
    stmt = (
        select(Message.id)
        .where(
            Message.conversation_id == conversation_id,
            Message.role == "assistant",
        )
        .order_by(desc(Message.created_at), desc(Message.id))
        .limit(1)
    )
    target = (await db.execute(stmt)).scalar_one_or_none()
    if not target:
        return False
    await db.execute(delete(Message).where(Message.id == target))
    return True


async def latest_assistant_finish_reason(
    db: AsyncSession, *, conversation_id: UUID,
) -> str | None:
    """Return finish_reason of the most recent assistant message ("length"
    if truncated by max_tokens), or None. Used by chat continuation detection:
    when user sends "继续" / "接着说" and last assistant was truncated, the
    prompt layer adds a hint instructing the model to seamlessly continue
    from the truncation point instead of starting over."""
    stmt = (
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.role == "assistant",
        )
        .order_by(desc(Message.created_at), desc(Message.id))
        .limit(1)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if not row or not row.meta:
        return None
    fr = row.meta.get("finish_reason") if isinstance(row.meta, dict) else None
    return fr if isinstance(fr, str) and fr else None


def _prompt_message_cost(item: dict) -> int:
    return len(str(item.get("role") or "")) + len(str(item.get("content") or ""))


async def context_chat_history(
    db: AsyncSession, *,
    conversation_id: UUID,
    max_messages: int = CHAT_CONTEXT_MAX_MESSAGES,
    char_budget: int = CHAT_CONTEXT_CHAR_BUDGET,
    always_keep: int = CHAT_CONTEXT_ALWAYS_KEEP,
) -> list[dict]:
    """Longer prompt history for expert chat, bounded by a rough char budget.

    We fetch a reasonably large tail, always retain the latest ``always_keep``
    messages, then fill older turns backwards until the budget is reached.
    Returned order is chronological and role/content shaped for prompts.
    """
    max_messages = max(1, min(int(max_messages), 200))
    char_budget = max(0, int(char_budget))
    always_keep = max(0, min(int(always_keep), max_messages))

    stmt = (
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.role.in_(["user", "assistant"]),
        )
        .order_by(desc(Message.created_at), desc(Message.id))
        .limit(max_messages)
    )
    rows = (await db.execute(stmt)).scalars().all()
    rows.reverse()  # chronological
    items = [{"role": m.role, "content": m.content or ""} for m in rows]
    if len(items) <= always_keep:
        return items

    recent_tail = items[-always_keep:] if always_keep else []
    older = items[:-always_keep] if always_keep else items
    used = sum(_prompt_message_cost(item) for item in recent_tail)
    selected_older: list[dict] = []

    for item in reversed(older):
        item_cost = _prompt_message_cost(item)
        if used + item_cost > char_budget:
            break
        selected_older.append(item)
        used += item_cost

    selected_older.reverse()
    return selected_older + recent_tail


async def delete_last_cta(
    db: AsyncSession, *, conversation_id: UUID,
) -> Optional[UUID]:
    """Atomic DELETE of the most recent role='cta' row. Returns deleted id or None.

    Used by chat (bypass_divination=True) and gua (consume on cast). Caller commits.
    NOTE: spec §5.4 / §6.1 step 10.
    """
    stmt = (
        select(Message.id)
        .where(Message.conversation_id == conversation_id, Message.role == "cta")
        .order_by(desc(Message.created_at), desc(Message.id))
        .limit(1)
    )
    last_id = (await db.execute(stmt)).scalar_one_or_none()
    if last_id is None:
        return None
    await db.execute(
        Message.__table__.delete().where(Message.id == last_id)
    )
    return last_id
