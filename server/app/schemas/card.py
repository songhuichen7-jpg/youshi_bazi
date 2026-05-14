"""Pydantic request/response schemas for the share-card API."""
from __future__ import annotations

import re
from datetime import datetime as _datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

_HTML_TAG_RE = re.compile(r"<[^>]+>")


class BirthInput(BaseModel):
    year: int = Field(ge=1900, le=2100)
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    hour: int = Field(ge=-1, le=23, description="-1 indicates 'time unknown'")
    minute: int = Field(ge=0, le=59, default=0)
    city: Optional[str] = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def _validate_calendar_date(self) -> "BirthInput":
        # 字段级 ge/le 只能保证 day∈[1,31]、month∈[1,12] 各自合法，但组合
        # 起来如 2025-02-29 / 2024-04-31 还是非法日历日。这种入参以前会
        # 沿到 paipan.compute → lunar_python.Solar → datetime() 抛 ValueError，
        # FastAPI 兜不住直接 500。在这里早一步用 datetime 试构造，转成
        # ValidationError 让 FastAPI 自动 422 + 字段级错误。
        try:
            _datetime(self.year, self.month, self.day)
        except ValueError as e:
            raise ValueError(
                f"invalid date: {self.year}-{self.month:02d}-{self.day:02d} "
                f"is not a real calendar day ({e})"
            ) from e
        return self


class CardRequest(BaseModel):
    birth: BirthInput
    nickname: Optional[str] = Field(default=None, max_length=10)

    @field_validator("nickname", mode="before")
    @classmethod
    def _strip_html(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        cleaned = _HTML_TAG_RE.sub("", str(v)).strip()
        return cleaned or None


Precision = Literal["4-pillar", "3-pillar"]
State = Literal["绽放", "蓄力"]


class CardResponse(BaseModel):
    type_id: str
    cosmic_name: str
    base_name: str
    state: State
    state_icon: str
    day_stem: str
    one_liner: str
    ge_ju: str
    suffix: str
    subtags: list[str] = Field(min_length=3, max_length=3)
    golden_line: str
    personality_tag: str
    theme_color: str
    card_bg: str
    glow: str
    illustration_url: str
    reconstruction: str
    background_desc: str
    precision: Precision
    borderline: bool
    share_slug: str
    nickname: Optional[str]
    version: str
