"""Payment provider registry.

``get_provider(name)`` 根据 settings.payment_provider 返回单例。新加渠道时：
  1. 在 ``providers/<name>.py`` 实现 PaymentProvider 协议
  2. 把 (name, factory) 加到 ``_REGISTRY`` 字典
  3. 在 ``app.core.config.Settings.payment_provider`` Literal 里加这个名字

provider 实例是无状态的（业务状态在 service.py 里通过 db 事务管理），
所以单例就是 ``providers/<name>.py`` 顶层的对象。
"""
from __future__ import annotations

from typing import Callable

from app.billing.providers.base import PaymentProvider
from app.billing.providers.manual import provider as _manual_provider


def _wechat_factory() -> PaymentProvider:
    from app.billing.providers.wechat import provider
    return provider


def _alipay_factory() -> PaymentProvider:
    from app.billing.providers.alipay import provider
    return provider


_REGISTRY: dict[str, Callable[[], PaymentProvider]] = {
    "manual": lambda: _manual_provider,
    "wechat": _wechat_factory,
    "alipay": _alipay_factory,
}


def get_provider(name: str) -> PaymentProvider:
    factory = _REGISTRY.get(name)
    if factory is None:
        raise ValueError(f"Unknown payment provider: {name}")
    return factory()
