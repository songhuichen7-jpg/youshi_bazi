"""Minimal paipan accessors — tolerant of v1 flat / nested chart shapes.

Mirrors the accessor logic in retrieval2.intents but trimmed to the four
fields the family lookup retrievers actually need.
"""
from __future__ import annotations

from typing import Any


def _paipan(chart: Any) -> dict:
    if not isinstance(chart, dict):
        return {}
    return chart.get("PAIPAN") or chart.get("paipan") or chart


def _sizhu(chart: Any) -> dict:
    p = _paipan(chart)
    sz = p.get("sizhu") or p.get("siZhu") or {}
    return sz if isinstance(sz, dict) else {}


def _meta(chart: Any) -> dict:
    p = _paipan(chart)
    m = p.get("META") or p.get("meta") or {}
    return m if isinstance(m, dict) else {}


def _pillar(chart: Any, key: str) -> str:
    p = _paipan(chart)
    v = str(_sizhu(p).get(key) or "")
    return v if len(v) == 2 else ""


def _gan_of(chart: Any, key: str) -> str:
    v = _pillar(chart, key)
    return v[0] if v else ""


def _zhi_of(chart: Any, key: str) -> str:
    v = _pillar(chart, key)
    return v[1] if v else ""


def day_gan(chart: Any) -> str:
    rg = str(_meta(chart).get("rizhuGan") or _meta(chart).get("dayGan") or "")
    if rg:
        return rg[0]
    return _gan_of(chart, "day")


def day_zhi(chart: Any) -> str:
    return _zhi_of(chart, "day")


def day_pillar(chart: Any) -> str:
    g = day_gan(chart)
    z = day_zhi(chart)
    return g + z if g and z else ""


def month_gan(chart: Any) -> str:
    return _gan_of(chart, "month")


def month_zhi(chart: Any) -> str:
    return _zhi_of(chart, "month")


def year_gan(chart: Any) -> str:
    return _gan_of(chart, "year")


def year_zhi(chart: Any) -> str:
    return _zhi_of(chart, "year")


def hour_pillar(chart: Any) -> str:
    return _pillar(chart, "hour")


def hour_gan(chart: Any) -> str:
    return _gan_of(chart, "hour")


def hour_zhi(chart: Any) -> str:
    return _zhi_of(chart, "hour")


def four_zhi(chart: Any) -> tuple[str, str, str, str]:
    """Year/month/day/hour earth branches as a 4-tuple. Missing pillars
    yield empty strings."""
    return (year_zhi(chart), month_zhi(chart), day_zhi(chart), hour_zhi(chart))


def four_gan(chart: Any) -> tuple[str, str, str, str]:
    """Year/month/day/hour heavenly stems as a 4-tuple."""
    return (year_gan(chart), month_gan(chart), day_gan(chart), hour_gan(chart))
