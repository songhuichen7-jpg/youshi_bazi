"""'manual' provider — internal beta 的兜底，不实际收款。

行为：
  - ``start_checkout`` 返回 ``kind='mailto'`` — 前端渲染成"联系作者升级"，
    点击后打开邮件客户端，作者在邮件里看到 payment_id 后调
    ``POST /api/admin/subscriptions/grant`` 人工开通。
  - ``parse_webhook`` 永远 raise — 这条 provider 不接外部回调。

接入正式渠道前所有用户都走这条；接入后老 manual payment 的状态机不影响
（finalize_checkout / refund 都是 provider-agnostic 的）。
"""
from __future__ import annotations

from app.billing.providers.base import (
    CheckoutInstructions,
    PaymentProvider,
    WebhookEvent,
)


class _ManualProvider:
    name = "manual"
    enabled = True       # 总是可以启动 checkout（fallback 用）

    def start_checkout(
        self,
        *,
        payment_id: str,
        plan: str,
        period: str,
        amount_cents: int,
        user_id: str,
    ) -> CheckoutInstructions:
        amount_yuan = amount_cents / 100
        subject = f"有时 · 开通 {plan} ({period})"
        body = (
            f"我想开通 {plan} 订阅（{period}，¥{amount_yuan:.2f}）。\n"
            f"Payment id: {payment_id}\n"
            f"User id:    {user_id}\n"
        )
        return CheckoutInstructions(
            kind="mailto",
            payload={
                "to": "songhuichen7@gmail.com",
                "subject": subject,
                "body": body,
                "payment_id": payment_id,
            },
        )

    def parse_webhook(
        self,
        *,
        headers: dict[str, str],
        body: bytes,
    ) -> WebhookEvent:
        raise NotImplementedError(
            "manual provider 不接 webhook — 由 admin endpoint 直接 confirm"
        )


provider: PaymentProvider = _ManualProvider()
