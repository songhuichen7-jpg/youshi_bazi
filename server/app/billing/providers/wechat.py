"""微信支付 V3 provider — stub。

接入清单（拿到商户号后按这个列表填）：
  1. 申请商户号 + API V3 密钥 + 平台证书
  2. 在 .env 里填 WECHAT_PAY_MCH_ID / WECHAT_PAY_API_V3_KEY /
     WECHAT_PAY_PRIVATE_KEY_PATH / WECHAT_PAY_SERIAL_NO / WECHAT_PAY_NOTIFY_URL
  3. 在 ``app.core.config.Settings.payment_provider`` 默认值改为 'wechat'
  4. 实现下面的 _WechatProvider 两个方法 — 推荐用 ``wechatpayv3`` 包，
     避免自己写 RSA / SHA256 签名。

start_checkout 流程（Native 扫码）：
  POST /v3/pay/transactions/native
  body: { appid, mchid, description, out_trade_no=payment_id,
          notify_url, amount: { total: amount_cents } }
  response: { code_url }     ← 前端把这个 URL 渲染成二维码

parse_webhook 流程：
  - 验签：从 Wechatpay-Serial 头取证书序号，用对应平台证书验 RSA 签名
  - 解密 resource.ciphertext（AES-256-GCM, key=API V3 key）
  - 解析 trade_state；映射到 PaymentEventStatus
  - 回调要 idempotent：service 层用 provider_payment_id (=transaction_id)
    去重，所以这边只管解析
"""
from __future__ import annotations

from app.billing.providers.base import (
    CheckoutInstructions,
    PaymentProvider,
    WebhookEvent,
)
from app.core.config import settings


class _WechatProvider:
    name = "wechat"

    @property
    def enabled(self) -> bool:
        return bool(
            settings.wechat_pay_mch_id
            and settings.wechat_pay_api_v3_key
            and settings.wechat_pay_private_key_path
            and settings.wechat_pay_serial_no
            and settings.wechat_pay_notify_url
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
                "wechat provider 未配置 — 请补齐 settings.wechat_pay_* 五个字段后再启用"
            )
        # TODO: 拿到商户号后用 wechatpayv3 客户端调 /v3/pay/transactions/native
        # code_url = client.pay(...)['code_url']
        # return CheckoutInstructions(kind='qr_code', payload={'code_url': code_url, ...})
        raise NotImplementedError("wechat 商户号待接入")

    def parse_webhook(
        self,
        *,
        headers: dict[str, str],
        body: bytes,
    ) -> WebhookEvent:
        if not self.enabled:
            raise NotImplementedError(
                "wechat provider 未配置 — 接入回调前请先完成 start_checkout 配置"
            )
        # TODO: 验签 + 解密；映射 trade_state ∈ {SUCCESS, REFUND, ...} 到 our status
        raise NotImplementedError("wechat 回调待接入")


provider: PaymentProvider = _WechatProvider()
