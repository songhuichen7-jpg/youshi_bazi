"""Plan 6: message item + paginated list."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel

MessageRole = Literal["user", "assistant", "gua", "cta"]


class MessageDetail(BaseModel):
    id: UUID
    role: MessageRole
    content: Optional[str]
    meta: Optional[dict[str, Any]]
    created_at: datetime


class MessagesListResponse(BaseModel):
    items: list[MessageDetail]
    next_cursor: Optional[UUID]
