"""Plan 5 chart LLM request bodies.

- SectionBody: used by POST /api/charts/:id/sections
- LiunianBody: used by POST /api/charts/:id/liunian

verdicts / dayun / chips / recompute: no body (path / query params only).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# NOTE: spec §2.1 — 7 sections fixed literal
Section = Literal[
    "career", "personality", "wealth", "relationship",
    "health", "appearance", "special",
]


class SectionBody(BaseModel):
    section: Section


class LiunianBody(BaseModel):
    # NOTE: 上层 service 再校验 index 是否在 paipan.dayun 范围内
    dayun_index: int = Field(..., ge=0)
    year_index: int = Field(..., ge=0)
