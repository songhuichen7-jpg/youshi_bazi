"""HTTP layer for /api/billing/*.

End-user surface:
  GET  /api/billing/me          — 当前订阅快照 + provider 名（前端决定 CTA）
  POST /api/billing/checkout    — 发起 checkout，返回 instructions
  POST /api/billing/cancel      — 取消当前活动订阅
  POST /api/billing/webhook/{provider} — 渠道异步回调（无 auth；签名验证）

Admin surface:
  POST /api/admin/subscriptions/grant  — 人工开通（已经 grant 的会先 cancel 再开新条）
"""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user, require_admin
from app.billing import service as billing_service
from app.billing.providers import get_provider
from app.core.config import settings
from app.core.db import get_db
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.billing import (
    CancelSubscriptionRequest,
    CheckoutInstructionsResponse,
    CheckoutRequest,
    CheckoutResponse,
    GrantSubscriptionRequest,
    MyBillingResponse,
    SubscriptionResponse,
)
from app.services import subscription as subscription_service

router = APIRouter(prefix="/api/billing", tags=["billing"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin"])


def _serialize_subscription(sub: Subscription) -> SubscriptionResponse:
    return SubscriptionResponse(
        id=sub.id,
        plan=sub.plan,
        status=sub.status,
        source=sub.source,
        starts_at=sub.starts_at,
        ends_at=sub.ends_at,
        canceled_at=sub.canceled_at,
    )


@router.get("/me", response_model=MyBillingResponse)
async def my_billing_endpoint(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> MyBillingResponse:
    active = await subscription_service.get_active(db, user.id)
    last_payment = await billing_service.latest_payment_for_user(db, user.id)
    pending_id = last_payment.id if (last_payment and last_payment.status == "pending") else None
    return MyBillingResponse(
        plan=user.plan,
        plan_expires_at=user.plan_expires_at,
        active_subscription=_serialize_subscription(active) if active else None,
        pending_payment_id=pending_id,
        payment_provider=settings.payment_provider,
    )


@router.post("/checkout", response_model=CheckoutResponse)
async def checkout_endpoint(
    body: CheckoutRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> CheckoutResponse:
    provider_name = body.provider or settings.payment_provider
    try:
        result = await billing_service.start_checkout(
            db, user=user, plan=body.plan, period=body.period,
            provider_name=provider_name,
        )
    except NotImplementedError as e:
        # provider 配置缺失 — 让前端 fallback 到 manual
        raise HTTPException(503, detail={
            "code": "PROVIDER_UNAVAILABLE",
            "message": "支付渠道暂未配置，请联系作者人工开通",
            "details": {"provider": provider_name, "reason": str(e)},
        }) from e
    except ValueError as e:
        raise HTTPException(400, detail={
            "code": "VALIDATION", "message": str(e),
        }) from e
    await db.commit()
    return CheckoutResponse(
        payment_id=result.payment.id,
        amount_cents=result.payment.amount_cents,
        currency=result.payment.currency,
        instructions=CheckoutInstructionsResponse(
            kind=result.instructions.kind,
            payload=result.instructions.payload,
        ),
    )


@router.post("/cancel")
async def cancel_endpoint(
    body: CancelSubscriptionRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    active = await subscription_service.get_active(db, user.id)
    if active is None:
        raise HTTPException(404, detail={
            "code": "NO_ACTIVE_SUBSCRIPTION",
            "message": "当前没有活动订阅",
        })
    # 取消但保留 ends_at — 用户用到期那天为止仍是当前档位；之后 cron 会降回 lite。
    # cascade_user=False 避免立即降档（用户还想用完已付费的天数）。
    await subscription_service.revoke(
        db, sub=active, reason=body.reason or "user_cancel",
        cascade_user=False,
    )
    await db.commit()
    return {"ok": True, "ends_at": active.ends_at.isoformat() if active.ends_at else None}


@router.post("/webhook/{provider_name}")
async def webhook_endpoint(
    provider_name: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """支付渠道异步通知。无 auth — 用签名验证（每个 provider 各自实现）。

    payment_id / plan / period 从我们 ``out_trade_no`` / 自定义 attach 字段
    解出来 — 各 provider 实现里要把这两个 metadata 塞回 WebhookEvent.raw 才能
    走通确认流程。这里先做最少假设，等具体 provider 接入时再补。
    """
    if provider_name not in ("wechat", "alipay"):
        # manual 不接 webhook — 通过 admin endpoint 确认
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Not found"})
    try:
        provider = get_provider(provider_name)
    except ValueError as e:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": str(e)}) from e

    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        event = provider.parse_webhook(headers=headers, body=body)
    except NotImplementedError:
        raise HTTPException(503, detail={
            "code": "PROVIDER_UNAVAILABLE",
            "message": f"{provider_name} 渠道未启用",
        })
    except ValueError as e:
        # 验签失败 — 可能是恶意请求或签名密钥错配
        raise HTTPException(401, detail={
            "code": "WEBHOOK_VERIFY_FAILED",
            "message": str(e),
        }) from e

    # event.raw 里必须带 metadata.payment_id / .plan / .period — provider 实现负责把
    # 这些放进去（自定义 attach 字段 / out_trade_no 等）
    payment_id = event.raw.get("payment_id") if isinstance(event.raw, dict) else None
    plan = event.raw.get("plan") if isinstance(event.raw, dict) else None
    period = event.raw.get("period") if isinstance(event.raw, dict) else None
    if not (payment_id and plan and period):
        raise HTTPException(400, detail={
            "code": "WEBHOOK_MISSING_METADATA",
            "message": "回调缺少 payment_id / plan / period",
            "details": {"raw_keys": list(event.raw.keys()) if isinstance(event.raw, dict) else []},
        })
    try:
        await billing_service.confirm_payment(
            db, payment_id=UUID(payment_id), plan=plan, period=period, event=event,
        )
    except ValueError as e:
        raise HTTPException(404, detail={
            "code": "PAYMENT_NOT_FOUND",
            "message": str(e),
        }) from e
    await db.commit()
    # 多数渠道期望 200 + 简单 ack（具体格式各异；接入时按文档调整）
    return Response(content=json.dumps({"code": "SUCCESS"}), media_type="application/json")


# ── Admin surface ────────────────────────────────────────────────────────


@admin_router.post("/subscriptions/grant", response_model=SubscriptionResponse)
async def admin_grant_endpoint(
    body: GrantSubscriptionRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    target = await db.get(User, body.user_id)
    if target is None:
        raise HTTPException(404, detail={
            "code": "USER_NOT_FOUND", "message": "用户不存在",
        })
    sub = await subscription_service.grant_manual_subscription(
        db, user=target, plan=body.plan, ends_at=body.ends_at, note=body.note,
    )
    await db.commit()
    return _serialize_subscription(sub)
