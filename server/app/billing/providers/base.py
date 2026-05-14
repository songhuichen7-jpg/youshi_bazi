"""PaymentProvider — 接入新支付渠道时的最小契约。

所有渠道差异都收敛在这两个方法上：
  ``start_checkout`` — 把一个 pending Payment（已写库）翻译成渠道认识的
    prepay 请求，返回前端 / SDK 需要的拼装参数。
  ``parse_webhook`` — 验签并解析渠道回调，返回 (provider_payment_id, status)
    或抛异常。service 层拿到结果后更新 Payment / Subscription。

Provider 实例无状态 — 业务状态在 service 层用 db 事务管理；provider 只是
"翻译器"。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


PaymentEventStatus = Literal["succeeded", "failed", "refunded"]


@dataclass(frozen=True)
class CheckoutInstructions:
    """前端 / SDK 渲染 checkout UI 所需的最小信息。

    - ``kind`` 标明前端该怎么渲染：
        - 'qr_code'     — 渲染 ``payload.code_url`` 成二维码
        - 'redirect'    — window.location = ``payload.redirect_url``
        - 'mailto'      — 走联系作者 fallback（manual provider）
        - 'sdk_params'  — 拿 ``payload`` 调对应 JS-SDK
    - ``payload`` 是 dict，渲染端按 ``kind`` 解读。
    """
    kind: Literal["qr_code", "redirect", "mailto", "sdk_params"]
    payload: dict


@dataclass(frozen=True)
class WebhookEvent:
    """归一化后的回调结果 — service 层用它推动状态机。"""
    provider_payment_id: str    # 渠道侧的 payment id，用来 idempotent
    status: PaymentEventStatus
    raw: dict                   # 原始 payload，落库到 payments.raw_payload 上


class PaymentProvider(Protocol):
    name: str                   # 'manual' / 'wechat' / 'alipay'
    enabled: bool               # 是否能真正发起 checkout（缺凭据时为 False）

    def start_checkout(
        self,
        *,
        payment_id: str,        # 我们这边的 payments.id (UUID 字符串)
        plan: str,
        period: str,
        amount_cents: int,
        user_id: str,
    ) -> CheckoutInstructions:
        """根据本地 payment 调渠道发起 prepay，返回前端展示用的 instructions。"""
        ...

    def parse_webhook(
        self,
        *,
        headers: dict[str, str],
        body: bytes,
    ) -> WebhookEvent:
        """验签 + 解析回调。验签失败请抛 ``ValueError`` — 上层映射 401。"""
        ...
