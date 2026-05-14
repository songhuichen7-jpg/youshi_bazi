"""Provider-agnostic billing service.

业务状态机：
  start_checkout(user, plan, period, provider)
    → INSERT payments(status='pending', provider, amount_cents, ...)
    → provider.start_checkout(payment_id) → instructions
    → 返回 (payment, instructions) 给 API 层

  confirm_payment(payment_id, status, provider_payment_id)
    ← 调用方：webhook 或 admin endpoint
    → 当 status='succeeded' 且当前 status='pending'：
      • UPDATE payment.status = 'succeeded', paid_at, provider_payment_id
      • subscription_service.grant_manual_subscription（即使是 wechat 也走这条；
        manual 只是个 source 标签）— 但要带正确的 source 字符串
      • 把 payment.subscription_id 反向连上去
    → 失败状态走对应分支

幂等：用 ``provider_payment_id`` 在 payments 表上的 UNIQUE 来去重。webhook
重试时 INSERT/UPDATE 各自的 ON CONFLICT 行为决定结果。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.pricing import Period, Plan, period_end, price_cents
from app.billing.providers import get_provider
from app.billing.providers.base import CheckoutInstructions, WebhookEvent
from app.models.subscription import Payment, Subscription
from app.models.user import User
from app.services import subscription as subscription_service


# 渠道 → subscription / payment 表里 source 字段的对应关系。
_SUBSCRIPTION_SOURCE_BY_PROVIDER: dict[str, str] = {
    "manual": "manual_grant",
    "wechat": "wechat",
    "alipay": "alipay",
}


@dataclass(frozen=True)
class CheckoutResult:
    payment: Payment
    instructions: CheckoutInstructions


async def start_checkout(
    db: AsyncSession,
    *,
    user: User,
    plan: Plan,
    period: Period,
    provider_name: str,
) -> CheckoutResult:
    """创建一条 pending payment，让 provider 翻译成 prepay 信息。caller commits."""
    if plan not in ("standard", "pro"):
        raise ValueError(f"checkout plan must be standard|pro, got {plan!r}")
    if period not in ("monthly", "annual"):
        raise ValueError(f"checkout period must be monthly|annual, got {period!r}")

    provider = get_provider(provider_name)
    amount = price_cents(plan, period)

    payment = Payment(
        user_id=user.id,
        amount_cents=amount,
        currency="CNY",
        status="pending",
        provider=provider_name,
        # raw_payload 在 confirm_payment 阶段填上 webhook body
    )
    db.add(payment)
    await db.flush()                # 拿到 payment.id

    instructions = provider.start_checkout(
        payment_id=str(payment.id),
        plan=plan,
        period=period,
        amount_cents=amount,
        user_id=str(user.id),
    )
    return CheckoutResult(payment=payment, instructions=instructions)


async def confirm_payment(
    db: AsyncSession,
    *,
    payment_id: UUID,
    plan: Plan,
    period: Period,
    event: WebhookEvent,
) -> Payment:
    """webhook / admin 确认收款 — 用 provider_payment_id 幂等。

    成功路径：
      1. UPDATE payment.status='succeeded'
      2. 调 subscription_service.grant_manual_subscription（语义上 "记一段
         订阅 + 同步 user.plan"，名字带 manual 是历史 — 实际上对所有渠道通用）
      3. 把 payment.subscription_id 写回

    幂等：如果 payment 已经 succeeded 且 provider_payment_id 一致，直接返回。
    """
    payment = await db.get(Payment, payment_id)
    if payment is None:
        raise ValueError(f"payment {payment_id} not found")

    # 幂等 — 重复 webhook 直接放过
    if payment.status == "succeeded" and payment.provider_payment_id == event.provider_payment_id:
        return payment

    payment.status = event.status
    payment.provider_payment_id = event.provider_payment_id
    payment.raw_payload = event.raw

    if event.status == "succeeded":
        payment.paid_at = datetime.now(tz=timezone.utc)
        # 更新订阅 + user.plan
        user = await db.get(User, payment.user_id)
        if user is None:
            # 用户被删过了 — 钱收了但记不到订阅。落 status='succeeded' 备查。
            await db.flush()
            return payment
        ends_at = period_end(period)
        sub = await subscription_service.grant_manual_subscription(
            db, user=user, plan=plan, ends_at=ends_at,
        )
        # source 字段现场改一下 — grant_manual_subscription 默认写 'manual_grant'
        sub.source = _SUBSCRIPTION_SOURCE_BY_PROVIDER.get(payment.provider, "manual_grant")
        payment.subscription_id = sub.id
    elif event.status in ("failed", "refunded"):
        # 失败 / 退款不动 user.plan — 退款场景另外有 revoke_subscription 的入口
        pass

    await db.flush()
    return payment


async def latest_payment_for_user(
    db: AsyncSession, user_id: UUID,
) -> Optional[Payment]:
    """最近一笔 payment — 给 /api/billing/me 用。"""
    result = await db.execute(
        select(Payment)
        .where(Payment.user_id == user_id)
        .order_by(Payment.created_at.desc())
        .limit(1)
    )
    return cast(Optional[Payment], result.scalar_one_or_none())
