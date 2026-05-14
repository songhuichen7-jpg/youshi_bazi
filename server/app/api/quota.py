"""GET /api/quota — current Beijing-day quota snapshot for the authenticated user."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.core.db import get_db
from app.models.user import User
from app.schemas.quota import QuotaResponse
from app.services import quota as quota_service

router = APIRouter(tags=["quota"], dependencies=[Depends(current_user)])


@router.get("/api/quota", response_model=QuotaResponse)
async def get_quota(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> QuotaResponse:
    return await quota_service.get_snapshot(db, user)
