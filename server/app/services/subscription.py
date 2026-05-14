"""Subscription lifecycle helpers.

Three operations cover internal-beta需求：
  1. ``grant_manual_subscription`` — 作者手动给某用户开 standard / pro
     （内测期、个别 power user、补偿）。
  2. ``revoke`` — 撤销当前活动订阅（用户主动取消 / 误开通退还）。
  3. ``expire_due`` — 扫描所有 ``ends_at <= now`` 但还 ``status='active'`` 的
     订阅，翻成 ``expired`` 并把 user.plan 降回 lite — cron 调它，每小时
     一次足够（用量限制是日界，所以小时级 lag 没用户感知）。

每个操作都同步刷新 ``users.plan`` + ``users.plan_expires_at``，让 ``/api/auth/me``
能直接读 user.plan 不用再 JOIN 订阅表。订阅表是真相 of 历史，user.plan 是
读路径上的 cache。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Subscription
from app.models.user import User


SubscriptionPlan = str   # 'standard' | 'pro'
SubscriptionSource = str # 'manual_grant' | 'wechat' | 'alipay' | 'stripe' | ...


async def get_active(
    db: AsyncSession, user_id: UUID,
) -> Optional[Subscription]:
    """Returns the user's current active subscription, or None if they're on lite."""
    result = await db.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.status == "active",
        )
        .order_by(Subscription.created_at.desc())
    )
    return result.scalar_one_or_none()


async def grant_manual_subscription(
    db: AsyncSession,
    *,
    user: User,
    plan: SubscriptionPlan,
    ends_at: Optional[datetime] = None,
    note: Optional[str] = None,
) -> Subscription:
    """开通一段订阅，不挂任何渠道。

    如果用户已有活动订阅，就原地把那条 mark canceled 再开新条 — 保留账单
    历史的同时，避免一个 user 同时存在两条 active（部分索引会防止吗？不，
    部分索引允许多条 active；逻辑上禁止）。

    Caller commits.
    """
    existing = await get_active(db, user.id)
    if existing is not None:
        await _cancel_inplace(db, existing, reason="superseded_by_grant")

    sub = Subscription(
        user_id=user.id,
        plan=plan,
        status="active",
        source="manual_grant",
        ends_at=ends_at,
        cancel_reason=note,    # 用 cancel_reason 列暂兼记录开通备注；后期需要可拆字段
    )
    db.add(sub)
    await db.flush()

    user.plan = plan
    user.plan_expires_at = ends_at
    await db.flush()
    return sub


async def revoke(
    db: AsyncSession,
    *,
    sub: Subscription,
    reason: str,
    cascade_user: bool = True,
) -> None:
    """Mark the subscription canceled. If ``cascade_user``, demote user to lite
    (assumes the canceled sub was the active one)."""
    await _cancel_inplace(db, sub, reason=reason)
    if cascade_user:
        await db.execute(
            update(User)
            .where(User.id == sub.user_id)
            .values(plan="lite", plan_expires_at=None)
        )
        await db.flush()


async def expire_due(db: AsyncSession) -> int:
    """Scan & expire any subscription whose ``ends_at <= now`` is still active.
    Returns the number of subscriptions expired. Caller commits.

    For each expired sub, the corresponding user is demoted to lite (assuming
    they don't have another active sub — which currently can't exist since
    grant_manual cancels the previous one; webhook flows will need to revisit).
    """
    now = datetime.now(tz=timezone.utc)
    result = await db.execute(
        select(Subscription)
        .where(
            Subscription.status == "active",
            Subscription.ends_at.is_not(None),
            Subscription.ends_at <= now,
        )
    )
    expired = list(result.scalars().all())
    for sub in expired:
        sub.status = "expired"
        await db.execute(
            update(User)
            .where(User.id == sub.user_id)
            .values(plan="lite", plan_expires_at=None)
        )
    await db.flush()
    return len(expired)


async def _cancel_inplace(
    db: AsyncSession, sub: Subscription, *, reason: str,
) -> None:
    sub.status = "canceled"
    sub.canceled_at = datetime.now(tz=timezone.utc)
    sub.cancel_reason = reason
    await db.flush()
