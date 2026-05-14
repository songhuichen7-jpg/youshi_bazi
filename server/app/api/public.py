"""Public endpoints — no auth required.

/api/config → feature flags for the frontend to render with
/api/cities → full city list for frontend typeahead (cached via ETag)
"""
from __future__ import annotations

import hashlib
from functools import lru_cache

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

import paipan

from app.core.config import settings
from app.core.quotas import MAX_CHARTS_PER_USER
from app.schemas.config import CitiesResponse, CityItem, ConfigResponse

router = APIRouter(tags=["public"])


@router.get("/api/config", response_model=ConfigResponse)
async def get_config() -> ConfigResponse:
    return ConfigResponse(
        require_invite=settings.require_invite,
        engine_version=paipan.VERSION,
        max_charts_per_user=MAX_CHARTS_PER_USER,
        guest_login_enabled=settings.guest_login_available,
    )


@lru_cache(maxsize=1)
def _cities_payload() -> tuple[dict, str]:
    """Build the /api/cities payload once per process.

    Returns (serializable_dict, etag_quoted) — both cached.
    """
    items = paipan.all_cities()  # already name-sorted
    resp = CitiesResponse(items=[CityItem(name=n, lng=lng, lat=lat) for n, lng, lat in items])
    etag_raw = hashlib.sha1(f"{paipan.VERSION}:{len(items)}".encode("utf-8")).hexdigest()[:16]
    return resp.model_dump(mode="json"), f'"{etag_raw}"'


@router.get("/api/cities")
async def get_cities(request: Request) -> Response:
    payload, etag = _cities_payload()
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=304,
            headers={"ETag": etag, "Cache-Control": "public, max-age=86400"},
        )
    return JSONResponse(
        content=payload,
        headers={"ETag": etag, "Cache-Control": "public, max-age=86400"},
    )
