"""Billing package — provider-agnostic checkout / webhook flow.

The user-facing surface is in ``app.api.billing``; the provider-specific
glue lives under ``app.billing.providers.*``. Pricing constants are in
``app.billing.pricing``. Service-layer helpers (create checkout, confirm
payment, expire subscription) are in ``app.billing.service``.

Design：所有"付费"动作都过 ``service.start_checkout`` → 渠道返回 prepay
信息 → 用户去渠道完成支付 → webhook 进 ``service.confirm_payment`` →
更新 payment + subscription + ``users.plan``。manual 渠道把这套流程
全部内化在后端：作者通过 admin endpoint 直接调 ``confirm_payment``。
"""
