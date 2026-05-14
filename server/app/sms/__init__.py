"""SMS provider Protocol + lazy factory.

Factory picks DevSmsProvider unless all three aliyun_sms_* settings are set,
in which case it returns an AliyunSmsProvider. This means:
  - Tests: no credentials set → always DevSmsProvider → no real SMS.
  - Prod (Plan 7): all three set → AliyunSmsProvider (raises NotImplementedError
    until that plan's implementation lands).

The provider instance is cached module-level via functools.lru_cache to avoid
re-instantiating per request.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from app.core.config import settings
from app.sms.aliyun import AliyunSmsProvider
from app.sms.dev import DevSmsProvider


class SmsProvider(Protocol):
    async def send(self, phone: str, code: str) -> None: ...


@lru_cache(maxsize=1)
def get_sms_provider() -> SmsProvider:
    """Return the singleton provider for this process."""
    if (
        settings.aliyun_sms_access_key
        and settings.aliyun_sms_secret
        and settings.aliyun_sms_template
    ):
        return AliyunSmsProvider(
            access_key=settings.aliyun_sms_access_key,
            secret=settings.aliyun_sms_secret,
            template=settings.aliyun_sms_template,
        )
    return DevSmsProvider()


__all__ = ["SmsProvider", "DevSmsProvider", "AliyunSmsProvider", "get_sms_provider"]
