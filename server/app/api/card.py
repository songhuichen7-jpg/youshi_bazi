"""Card generation endpoint. Public (no auth). Writes a card_shares row per
generation for share-link preview + analytics."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.card_share import CardShare
from app.schemas.card import CardRequest, CardResponse
from app.services.card.loader import TYPES, illustration_url, load_all
from app.services.card.payload import build_card_payload
from app.services.card.slug import birth_hash

router = APIRouter(prefix="/api", tags=["card"])


@router.post("/card", response_model=CardResponse)
async def post_card(
    req: CardRequest,
    db: AsyncSession = Depends(get_db),
) -> CardResponse:
    # Ensure JSON data is loaded (safe under normal startup; this is a safety net).
    load_all()

    payload = build_card_payload(req.birth, req.nickname)

    share = CardShare(
        slug=payload.share_slug,
        birth_hash=birth_hash(
            req.birth.year, req.birth.month, req.birth.day,
            req.birth.hour, req.birth.minute,
        ),
        type_id=payload.type_id,
        cosmic_name=payload.cosmic_name,
        suffix=payload.suffix,
        nickname=payload.nickname,
        user_id=None,  # MVP: always anonymous
    )
    db.add(share)
    # get_db auto-commits on success — no explicit db.commit() needed here.

    return payload


class CardPreview(BaseModel):
    slug: str
    cosmic_name: str
    suffix: str
    illustration_url: str
    nickname: Optional[str]


@router.get("/card/{slug}", response_model=CardPreview)
async def get_card_preview(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> CardPreview:
    row = (await db.execute(
        select(CardShare).where(CardShare.slug == slug)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="card not found")

    info = TYPES[row.type_id]

    # Bump share_count (auto-committed by get_db dependency on return)
    row.share_count += 1

    return CardPreview(
        slug=row.slug,
        cosmic_name=row.cosmic_name,
        suffix=row.suffix,
        illustration_url=illustration_url(info["illustration"]),
        nickname=row.nickname,
    )
