"""HTTP-layer schemas for /api/billing/* endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


Plan = Literal["standard", "pro"]
Period = Literal["monthly", "annual"]


class CheckoutRequest(BaseModel):
    plan: Plan
    period: Period = "monthly"
    # 默认走 settings.payment_provider；显式传也允许（admin 试 different provider）
    provider: Optional[Literal["manual", "wechat", "alipay"]] = None


class CheckoutInstructionsResponse(BaseModel):
    kind: Literal["qr_code", "redirect", "mailto", "sdk_params"]
    payload: dict


class CheckoutResponse(BaseModel):
    payment_id: UUID
    amount_cents: int
    currency: str
    instructions: CheckoutInstructionsResponse


class SubscriptionResponse(BaseModel):
    id: UUID
    plan: str                # 'standard' | 'pro'
    status: str              # 'active' | 'canceled' | 'expired' | 'past_due'
    source: str
    starts_at: datetime
    ends_at: Optional[datetime]
    canceled_at: Optional[datetime]


class MyBillingResponse(BaseModel):
    """/api/billing/me — 当前订阅 + 最近一笔付款的状态。"""
    plan: Literal["lite", "standard", "pro"]
    plan_expires_at: Optional[datetime]
    active_subscription: Optional[SubscriptionResponse] = None
    pending_payment_id: Optional[UUID] = None     # 有未完成的 checkout 时填
    payment_provider: str                         # settings.payment_provider — 让前端决定 CTA 形态


class GrantSubscriptionRequest(BaseModel):
    """admin endpoint — 人工开通 / 续期。"""
    user_id: UUID
    plan: Plan
    ends_at: Optional[datetime] = None
    note: Optional[str] = Field(default=None, max_length=200)


class CancelSubscriptionRequest(BaseModel):
    """用户主动取消当前订阅 — 不退款，只是不再续；ends_at 之前还能用。"""
    reason: Optional[str] = Field(default=None, max_length=200)
