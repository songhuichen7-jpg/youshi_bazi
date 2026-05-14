"""Plan 5 quota snapshot response."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# NOTE: spec §2.2 / core/quotas.py QUOTAS dict keys
QuotaKind = Literal[
    "chat_message", "section_regen", "verdicts_regen",
    "dayun_regen", "liunian_regen", "gua", "sms_send",
]


class QuotaKindUsage(BaseModel):
    used: int
    limit: int
    resets_at: datetime      # next Beijing midnight


class QuotaResponse(BaseModel):
    plan: Literal["lite", "standard", "pro"]
    usage: dict[QuotaKind, QuotaKindUsage]      # 7 keys always present
