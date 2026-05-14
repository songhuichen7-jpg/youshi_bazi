"""HTTP layer for /api/auth/sessions — list + revoke."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.core.db import get_db
from app.models.user import User
from app.schemas.auth import SessionResponse
from app.services import session as session_service
from app.services.exceptions import ServiceError

router = APIRouter(prefix="/api/auth/sessions", tags=["auth"])


def _http_error(err: ServiceError) -> HTTPException:
    return HTTPException(status_code=err.status, detail=err.to_dict())


@router.get("", response_model=list[SessionResponse])
async def list_sessions_endpoint(
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionResponse]:
    rows = await session_service.list_sessions(db, user.id)
    current_session_id = request.state.session.id
    return [
        SessionResponse(
            id=s.id,
            user_agent=s.user_agent,
            ip=str(s.ip) if s.ip is not None else None,
            created_at=s.created_at,
            last_seen_at=s.last_seen_at,
            is_current=(s.id == current_session_id),
        )
        for s in rows
    ]


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session_endpoint(
    session_id: UUID,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        await session_service.revoke_session(db, user.id, session_id)
    except ServiceError as e:
        raise _http_error(e)

    # If the revoked session is the current one, clear the cookie too.
    if session_id == request.state.session.id:
        response.delete_cookie("session", path="/")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
