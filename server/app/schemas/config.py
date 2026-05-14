"""Public-endpoint schemas (/api/config + /api/cities)."""
from __future__ import annotations

from pydantic import BaseModel


class ConfigResponse(BaseModel):
    require_invite: bool
    engine_version: str
    max_charts_per_user: int
    guest_login_enabled: bool


class CityItem(BaseModel):
    name: str
    lng: float
    lat: float


class CitiesResponse(BaseModel):
    items: list[CityItem]
