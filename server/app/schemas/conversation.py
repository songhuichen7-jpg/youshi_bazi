"""Plan 6: conversation request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ConversationCreateRequest(BaseModel):
    label: Optional[str] = None
    hepan_slug: Optional[str] = None

    @field_validator("label")
    @classmethod
    def _strip_optional(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        return s or None

    @field_validator("hepan_slug")
    @classmethod
    def _strip_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        return s or None


class ConversationPatchRequest(BaseModel):
    label: str = Field(min_length=1)

    @field_validator("label")
    @classmethod
    def _must_be_nonblank(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("label must not be blank")
        return s


class ConversationDetail(BaseModel):
    id: UUID
    chart_id: UUID
    label: Optional[str]
    hepan_slug: Optional[str] = None
    position: int
    created_at: datetime
    updated_at: datetime
    last_message_at: Optional[datetime]
    message_count: int
    deleted_at: Optional[datetime]


class ConversationListResponse(BaseModel):
    items: list[ConversationDetail]
