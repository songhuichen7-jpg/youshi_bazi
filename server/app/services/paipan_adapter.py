"""Thin wrapper over paipan package.

Boundaries:
- Pydantic BirthInput → paipan.compute kwargs
- paipan.ValueError → InvalidBirthInput (HTTP 400)
- paipan.VERSION → cache staleness check
- get_city_coords → canonical name + coords

Warnings from paipan are returned in-band but NOT persisted — they track
paipan logic that may evolve across versions.
"""
from __future__ import annotations

from paipan import compute as paipan_compute
from paipan import VERSION as PAIPAN_VERSION
from paipan.cities import get_city_coords

from app.schemas.chart import BirthInput
from app.services.exceptions import InvalidBirthInput


def resolve_city(raw: str | None) -> dict | None:
    """Normalize a user-entered city name to {canonical, lng, lat}.

    Returns None for falsy / unresolved inputs.
    """
    # NOTE: spec §3.1 — service layer must re-normalize before persisting;
    # don't trust client-side values.
    if raw is None or not str(raw).strip():
        return None
    c = get_city_coords(raw)
    if c is None:
        return None
    return {"canonical": c.canonical, "lng": c.lng, "lat": c.lat}


def run_paipan(birth: BirthInput) -> tuple[dict, list[str], str]:
    """Invoke paipan.compute and split warnings out of the result dict.

    Returns (paipan_dict, warnings, engine_version). The returned paipan_dict
    has no 'warnings' key — caller is responsible for forwarding warnings to
    the API response if desired (not persisted).
    """
    try:
        result = paipan_compute(**birth.model_dump())
    except ValueError as e:
        # NOTE: paipan internals raise ValueError only on genuinely bad input
        # (invalid ganzhi / zhi); surface as HTTP 400.
        raise InvalidBirthInput(str(e)) from e

    warnings = result.pop("warnings", []) or []
    return result, list(warnings), PAIPAN_VERSION


def is_cache_stale(chart_engine_version: str) -> bool:
    """True iff the chart was computed under a different paipan version."""
    return chart_engine_version != PAIPAN_VERSION
