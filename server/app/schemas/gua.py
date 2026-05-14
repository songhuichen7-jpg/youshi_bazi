"""Plan 6: POST /api/conversations/:id/gua request body."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class GuaCastRequest(BaseModel):
    question: str = Field(min_length=1)

    @field_validator("question")
    @classmethod
    def _strip(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("question must not be blank")
        return s
