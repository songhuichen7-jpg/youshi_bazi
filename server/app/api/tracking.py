"""Public tracking endpoint — anonymous event capture for K-factor analytics."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.event import Event
from app.models.user import UserSession
from app.schemas.tracking import TrackRequest

router = APIRouter(prefix="/api", tags=["tracking"])

_KNOWN_FIELDS = {
    "type_id", "channel", "from_", "share_slug",
    "anonymous_id", "session_id", "user_agent", "viewport",
}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def _resolve_user_id_from_cookie(request: Request, db: AsyncSession) -> UUID | None:
    """Best-effort user attribution for analytics.

    Tracking must stay public and non-blocking: a missing, expired, or invalid
    cookie simply means the event remains anonymous.
    """
    token = request.cookies.get("session")
    if not token:
        return None
    row = (await db.execute(
        select(UserSession.user_id).where(
            UserSession.token_hash == _sha256(token),
            UserSession.expires_at > datetime.now(tz=timezone.utc),
        )
    )).scalar_one_or_none()
    return row


@router.post("/track", status_code=204)
async def post_track(
    req: TrackRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    props = req.properties
    # Everything beyond KNOWN_FIELDS goes into extra JSONB
    extra_dump = props.model_dump(
        by_alias=True,
        exclude=_KNOWN_FIELDS,
        exclude_none=True,
    )
    evt = Event(
        event=req.event,
        type_id=props.type_id,
        channel=props.channel,
        from_param=props.from_,
        share_slug=props.share_slug,
        anonymous_id=props.anonymous_id,
        session_id=props.session_id,
        user_id=await _resolve_user_id_from_cookie(request, db),
        user_agent=props.user_agent,
        viewport=props.viewport,
        extra=extra_dump or None,
    )
    db.add(evt)
    # get_db auto-commits
    return Response(status_code=204)
