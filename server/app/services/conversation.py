"""Conversation CRUD + ownership + soft-delete/restore. NOTE: spec §4."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chart import Chart
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.conversation import ConversationDetail
from app.services.exceptions import (
    ConversationAlreadyDeletedError,
    ConversationGoneError,
    NotFoundError,
)


async def _get_owned_chart(db: AsyncSession, user: User, chart_id: UUID) -> Chart:
    """Returns active (non-soft-deleted) chart owned by user, else 404."""
    stmt = select(Chart).where(
        Chart.id == chart_id,
        Chart.user_id == user.id,
        Chart.deleted_at.is_(None),
    )
    chart = (await db.execute(stmt)).scalar_one_or_none()
    if chart is None:
        raise NotFoundError(message="命盘不存在")
    return chart


async def _get_owned_conversation_row(
    db: AsyncSession, user: User, conv_id: UUID,
    *, allow_deleted: bool = False,
) -> Conversation:
    """JOIN conversations → charts → user_id; 404 on miss/cross-user."""
    stmt = (
        select(Conversation)
        .join(Chart, Conversation.chart_id == Chart.id)
        .where(Conversation.id == conv_id, Chart.user_id == user.id,
               Chart.deleted_at.is_(None))
    )
    conv = (await db.execute(stmt)).scalar_one_or_none()
    if conv is None:
        raise NotFoundError(message="对话不存在")
    if conv.deleted_at is not None and not allow_deleted:
        raise NotFoundError(message="对话不存在")
    return conv


async def _to_detail(db: AsyncSession, conv: Conversation) -> ConversationDetail:
    """Build ConversationDetail with message_count + last_message_at."""
    row = (await db.execute(
        select(func.count(Message.id), func.max(Message.created_at))
        .where(Message.conversation_id == conv.id)
    )).one()
    return ConversationDetail(
        id=conv.id, chart_id=conv.chart_id, label=conv.label,
        hepan_slug=conv.hepan_slug,
        position=conv.position,
        created_at=conv.created_at, updated_at=conv.updated_at,
        last_message_at=row[1], message_count=int(row[0] or 0),
        deleted_at=conv.deleted_at,
    )


async def list_conversations(
    db: AsyncSession, user: User, chart_id: UUID,
) -> list[ConversationDetail]:
    chart = await _get_owned_chart(db, user, chart_id)

    msg_agg = (
        select(
            Message.conversation_id.label("cid"),
            func.count(Message.id).label("message_count"),
            func.max(Message.created_at).label("last_message_at"),
        )
        .group_by(Message.conversation_id)
        .subquery()
    )
    stmt = (
        select(
            Conversation,
            func.coalesce(msg_agg.c.message_count, 0).label("message_count"),
            msg_agg.c.last_message_at,
        )
        .outerjoin(msg_agg, Conversation.id == msg_agg.c.cid)
        .where(Conversation.chart_id == chart.id, Conversation.deleted_at.is_(None))
        .order_by(Conversation.position.asc(), Conversation.created_at.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        ConversationDetail(
            id=conv.id, chart_id=conv.chart_id, label=conv.label,
            hepan_slug=conv.hepan_slug,
            position=conv.position,
            created_at=conv.created_at, updated_at=conv.updated_at,
            last_message_at=last_at,
            message_count=int(count or 0),
            deleted_at=conv.deleted_at,
        )
        for conv, count, last_at in rows
    ]


async def create_conversation(
    db: AsyncSession, user: User, chart_id: UUID,
    *, label: Optional[str] = None, hepan_slug: Optional[str] = None,
) -> ConversationDetail:
    chart = await _get_owned_chart(db, user, chart_id)
    # next position = max(active positions) + 1, or 0 if no active convs
    pos_row = (await db.execute(
        select(func.coalesce(func.max(Conversation.position), -1))
        .where(Conversation.chart_id == chart.id, Conversation.deleted_at.is_(None))
    )).scalar_one()
    next_pos = int(pos_row) + 1
    if not label:
        # Default = "对话 N" where N = active count + 1
        cnt = (await db.execute(
            select(func.count(Conversation.id))
            .where(Conversation.chart_id == chart.id, Conversation.deleted_at.is_(None))
        )).scalar_one()
        label = f"对话 {int(cnt) + 1}"
    conv = Conversation(
        chart_id=chart.id,
        label=label,
        position=next_pos,
        hepan_slug=hepan_slug,
    )
    db.add(conv)
    await db.flush()
    return await _to_detail(db, conv)


async def get_conversation(
    db: AsyncSession, user: User, conv_id: UUID,
) -> ConversationDetail:
    conv = await _get_owned_conversation_row(db, user, conv_id, allow_deleted=True)
    return await _to_detail(db, conv)


async def patch_label(
    db: AsyncSession, user: User, conv_id: UUID, label: str,
) -> ConversationDetail:
    conv = await _get_owned_conversation_row(db, user, conv_id)
    conv.label = label
    conv.updated_at = datetime.now(tz=timezone.utc)
    await db.flush()
    return await _to_detail(db, conv)


async def soft_delete(db: AsyncSession, user: User, conv_id: UUID) -> None:
    conv = await _get_owned_conversation_row(db, user, conv_id, allow_deleted=True)
    if conv.deleted_at is not None:
        raise ConversationAlreadyDeletedError()
    conv.deleted_at = datetime.now(tz=timezone.utc)
    await db.flush()


async def restore(
    db: AsyncSession, user: User, conv_id: UUID,
) -> ConversationDetail:
    conv = await _get_owned_conversation_row(db, user, conv_id, allow_deleted=True)
    if conv.deleted_at is None:
        return await _to_detail(db, conv)
    # Use DB clock (matches chart.py restore semantics) for window check.
    cutoff_row = (await db.execute(
        text("SELECT now() - INTERVAL '30 days'")
    )).scalar_one()
    if conv.deleted_at < cutoff_row:
        raise ConversationGoneError()
    conv.deleted_at = None
    await db.flush()
    return await _to_detail(db, conv)
