"""Pydantic models for paipan inputs and outputs."""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


ZiConvention = Literal["early", "late"]
Gender = Literal["male", "female"]


class BirthInput(BaseModel):
    year: int
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    hour: int = Field(ge=-1, le=23)  # -1 = unknown
    minute: int = Field(default=0, ge=0, le=59)
    city: Optional[str] = None
    longitude: Optional[float] = None
    gender: Gender
    ziConvention: ZiConvention = "early"
    useTrueSolarTime: bool = True


class City(BaseModel):
    lng: float
    lat: float
    canonical: str
