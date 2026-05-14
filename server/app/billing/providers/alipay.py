"""支付宝 provider — stub。

接入清单：
  1. 商户应用 ID + 应用私钥 + 支付宝公钥（异步通知验签用）
  2. 配 ALIPAY_APP_ID / ALIPAY_APP_PRIVATE_KEY / ALIPAY_PUBLIC_KEY /
     ALIPAY_NOTIFY_URL
  3. settings.payment_provider = 'alipay'
  4. 推荐 ``python-alipay-sdk`` — 自己写 RSA2 签名容易出错

start_checkout 流程（PC 网站支付）：
  alipay.trade.page.pay → 返回 redirect_url
  → CheckoutInstructions(kind='redirect', payload={'redirect_url': url})

parse_webhook：
  POST 表单 → 用支付宝公钥验签 → 拿 trade_status；
  TRADE_SUCCESS / TRADE_FINISHED → 'succeeded'
  TRADE_CLOSED → 'failed'
"""
from __future__ import annotations

from app.billing.providers.base import (
    CheckoutInstructions,
    PaymentProvider,
    WebhookEvent,
)
from app.core.config import settings


class _AlipayProvider:
    name = "alipay"

    @property
    def enabled(self) -> bool:
        return bool(
            settings.alipay_app_id
            and settings.alipay_app_private_key
            and settings.alipay_public_key
            and settings.alipay_notify_url
        )

    def start_checkout(
        self,
        *,
        payment_id: str,
        plan: str,
        period: str,
        amount_cents: int,
        user_id: str,
    ) -> CheckoutInstructions:
        if not self.enabled:
            raise NotImplementedError(
                "alipay provider 未配置 — 请补齐 settings.alipay_* 四个字段后再启用"
            )
        # TODO: alipay.api_alipay_trade_page_pay(out_trade_no=payment_id, ...)
        raise NotImplementedError("alipay 商户应用待接入")

    def parse_webhook(
        self,
        *,
        headers: dict[str, str],
        body: bytes,
    ) -> WebhookEvent:
        if not self.enabled:
            raise NotImplementedError(
                "alipay provider 未配置 — 接入回调前请先完成 start_checkout 配置"
            )
        # TODO: 解析 form-urlencoded body + RSA2 验签 + 映射 trade_status
        raise NotImplementedError("alipay 回调待接入")


provider: PaymentProvider = _AlipayProvider()
