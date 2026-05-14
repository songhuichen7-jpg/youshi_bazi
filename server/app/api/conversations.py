"""HTTP layer for /api/conversations/* and /api/charts/:id/conversations.

Thin wrapper over services/conversation, services/message,
services/conversation_chat, and services/conversation_gua.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import check_quota, current_user
from app.core.db import get_db
from app.models.user import User
from app.schemas.chat import ChatMessageRequest
from app.schemas.conversation import (
    ConversationCreateRequest,
    ConversationDetail,
    ConversationListResponse,
    ConversationPatchRequest,
)
from app.schemas.gua import GuaCastRequest
from app.schemas.message import MessagesListResponse
from app.services import chart as chart_service
from app.services import conversation as conv_service
from app.services import conversation_chat as chat_svc
from app.services import conversation_gua as gua_svc
from app.services import message as msg_service
from app.services.exceptions import NotFoundError, ServiceError

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _http_error(err: ServiceError) -> HTTPException:
    return HTTPException(status_code=err.status, detail=err.to_dict())


# ---------------------------------------------------------------------------
# Router A: nested under /api/charts/:chart_id/conversations
# ---------------------------------------------------------------------------

charts_router = APIRouter(
    prefix="/api/charts",
    tags=["conversations"],
    dependencies=[Depends(current_user)],
)


@charts_router.post(
    "/{chart_id}/conversations",
    response_model=ConversationDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation_endpoint(
    chart_id: UUID,
    body: ConversationCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> ConversationDetail:
    try:
        detail = await conv_service.create_conversation(
            db, user, chart_id, label=body.label, hepan_slug=body.hepan_slug,
        )
        await db.commit()
    except ServiceError as e:
        await db.rollback()
        raise _http_error(e)
    return detail


@charts_router.get(
    "/{chart_id}/conversations",
    response_model=ConversationListResponse,
)
async def list_conversations_endpoint(
    chart_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> ConversationListResponse:
    try:
        items = await conv_service.list_conversations(db, user, chart_id)
    except ServiceError as e:
        raise _http_error(e)
    return ConversationListResponse(items=items)


# ---------------------------------------------------------------------------
# Router B: /api/conversations/:conv_id (flat, no chart prefix)
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/api/conversations",
    tags=["conversations"],
    dependencies=[Depends(current_user)],
)


@router.get("/{conv_id}", response_model=ConversationDetail)
async def get_conversation_endpoint(
    conv_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> ConversationDetail:
    try:
        detail = await conv_service.get_conversation(db, user, conv_id)
    except ServiceError as e:
        raise _http_error(e)
    return detail


@router.patch("/{conv_id}", response_model=ConversationDetail)
async def patch_conversation_endpoint(
    conv_id: UUID,
    body: ConversationPatchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> ConversationDetail:
    try:
        detail = await conv_service.patch_label(db, user, conv_id, body.label)
        await db.commit()
    except ServiceError as e:
        await db.rollback()
        raise _http_error(e)
    return detail


@router.delete("/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation_endpoint(
    conv_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    try:
        await conv_service.soft_delete(db, user, conv_id)
        await db.commit()
    except ServiceError as e:
        await db.rollback()
        raise _http_error(e)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{conv_id}/restore", response_model=ConversationDetail)
async def restore_conversation_endpoint(
    conv_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> ConversationDetail:
    try:
        detail = await conv_service.restore(db, user, conv_id)
        await db.commit()
    except ServiceError as e:
        await db.rollback()
        raise _http_error(e)
    return detail


@router.get("/{conv_id}/messages", response_model=MessagesListResponse)
async def list_messages_endpoint(
    conv_id: UUID,
    before: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> MessagesListResponse:
    # Ownership check — ensures conv belongs to this user.
    try:
        await conv_service.get_conversation(db, user, conv_id)
    except ServiceError as e:
        raise _http_error(e)

    try:
        result = await msg_service.paginate(
            db, conversation_id=conv_id, before=before, limit=limit
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"code": "VALIDATION", "message": str(e)})
    return MessagesListResponse(**result)


@router.post("/{conv_id}/messages")
async def post_message_endpoint(
    conv_id: UUID,
    body: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
    ticket=Depends(check_quota("chat_message")),
):
    """Stream SSE chat response for a conversation message."""
    try:
        conv = await conv_service.get_conversation(db, user, conv_id)
        if conv.deleted_at is not None:
            raise NotFoundError(message="对话不存在")
        chart = await chart_service.get_chart(db, user, conv.chart_id)
    except ServiceError as e:
        raise _http_error(e)

    async def _gen():
        async for raw in chat_svc.stream_message(
            db=db, user=user, conversation_id=conv_id,
            chart=chart, message=body.message,
            bypass_divination=body.bypass_divination,
            client_context=body.client_context,
            regenerate=body.regenerate,
            ticket=ticket,
        ):
            yield raw
        await db.commit()

    return StreamingResponse(_gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/{conv_id}/gua")
async def post_gua_endpoint(
    conv_id: UUID,
    body: GuaCastRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
    ticket=Depends(check_quota("gua")),
):
    """Stream SSE gua cast for a conversation."""
    try:
        conv = await conv_service.get_conversation(db, user, conv_id)
        if conv.deleted_at is not None:
            raise NotFoundError(message="对话不存在")
        chart = await chart_service.get_chart(db, user, conv.chart_id)
    except ServiceError as e:
        raise _http_error(e)

    async def _gen():
        async for raw in gua_svc.stream_gua(
            db=db, user=user, conversation_id=conv_id,
            chart=chart, question=body.question,
            ticket=ticket,
        ):
            yield raw
        await db.commit()

    return StreamingResponse(_gen(), media_type="text/event-stream", headers=_SSE_HEADERS)
