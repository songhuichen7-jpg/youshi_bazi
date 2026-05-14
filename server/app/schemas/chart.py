"""Pydantic request/response schemas for /api/charts/*.

Separate from app/models/chart.py (ORM). Encrypted fields (birth_input /
paipan / label) are encoded as plain dicts/strings here; the ORM layer
handles actual encryption transparently.
"""
from __future__ import annotations

from datetime import datetime
from datetime import datetime as _datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ---- request bodies ---------------------------------------------------


class BirthInput(BaseModel):
    """paipan.compute() kwargs 的 1:1 映射。字段名/类型完全沿用 paipan。"""

    # NOTE: spec §2.1 / paipan.compute() signature
    year: int = Field(..., ge=1900, le=2100)
    month: int = Field(..., ge=1, le=12)
    day: int = Field(..., ge=1, le=31)
    # hour=-1 表示时辰未知；其余 0..23
    hour: int = Field(..., ge=-1, le=23)
    minute: int = Field(0, ge=0, le=59)
    city: str | None = Field(None, max_length=40)
    longitude: float | None = Field(None, ge=-180, le=180)
    gender: Literal["male", "female"]
    ziConvention: Literal["early", "late"] = "early"
    useTrueSolarTime: bool = True

    @model_validator(mode="after")
    def _validate_calendar_date(self) -> "BirthInput":
        # 字段级 ge/le 只能验单字段，组合非法日（2025-02-29 / 2024-04-31）会
        # 沿到 paipan.compute → lunar_python.Solar → datetime() 抛 ValueError，
        # FastAPI 兜不住返 500。在 schema 层早一步拦下，转 ValidationError →
        # 自动 422 + 字段错误。
        try:
            _datetime(self.year, self.month, self.day)
        except ValueError as e:
            raise ValueError(
                f"invalid date: {self.year}-{self.month:02d}-{self.day:02d} "
                f"is not a real calendar day ({e})"
            ) from e
        return self


class ChartCreateRequest(BaseModel):
    birth_input: BirthInput
    label: str | None = Field(None, max_length=40)


class ChartLabelUpdateRequest(BaseModel):
    label: str | None = Field(None, max_length=40)


# ---- response bodies --------------------------------------------------


class CacheSlot(BaseModel):
    # 'classics' added in migration 0006 to cache the LLM-polished 古籍旁证
    # output. Schema must accept it or GET /charts/{id} 500s after the
    # first classics fetch (the cache row exists but schema rejects it).
    kind: Literal["verdicts", "section", "dayun_step", "liunian", "classics"]
    key: str
    has_cache: bool
    model_used: str | None = None
    regen_count: int = 0
    generated_at: datetime | None = None


class ChartListItem(BaseModel):
    id: UUID
    label: str | None
    engine_version: str
    cache_stale: bool
    created_at: datetime
    updated_at: datetime


class ChartDetail(BaseModel):
    id: UUID
    label: str | None
    birth_input: BirthInput
    paipan: dict
    engine_version: str
    created_at: datetime
    updated_at: datetime


class ChartResponse(BaseModel):
    chart: ChartDetail
    cache_slots: list[CacheSlot] = Field(default_factory=list)
    cache_stale: bool
    # POST 时含 paipan.warnings；其他路由为空
    warnings: list[str] = Field(default_factory=list)


class ChartListResponse(BaseModel):
    items: list[ChartListItem]


class PersonaQuote(BaseModel):
    """古人画像 — 200–400 字的整体性情 / 命格描写。"""
    quote: str            # 古文原文（允许 LLM 加标点 / 截取关键句 / 删邻句）
    plain: str            # 白话意译
    book: str             # 滴天髓 / 子平真诠 / 三命通会 / 渊海子平
    chapter: str          # 性情 / 论性情 / ...
    section: str | None = None  # "命例 12" / "孟春甲日" 等子定位
    tier: Literal["case", "general"]  # case=具体命例直接命中 general=论X通用判文
    fit_note: str         # ≤30 字的结构匹配说明，必须引用结构事实


class VerdictQuote(BaseModel):
    """古人定语 — ≤50 字的格局成败 / 用神得力短判文。"""
    quote: str
    book: str
    chapter: str


class ChartClassicsResponse(BaseModel):
    persona: PersonaQuote | None = None
    verdict: VerdictQuote | None = None
