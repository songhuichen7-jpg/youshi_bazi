"""Plan 6: POST /api/conversations/:id/messages request body."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1)
    bypass_divination: bool = False
    # True 表示这条 message 是"重新回答"——前端 chatHistory 已经把上一条
    # assistant 重置为空 placeholder，后端不应再 insert 新的 user 行（否则
    # DB 累积重复 user），而是删掉旧 assistant + 复用现有 user 直接重生。
    regenerate: bool = False
    client_context: dict[str, Any] | None = None

    @field_validator("message")
    @classmethod
    def _strip(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("message must not be blank")
        return s
