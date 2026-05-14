"""Aliyun SMS provider — skeleton. Real API call lands in Plan 7 deployment.

The real integration requires ICP filing + aliyun account + signed SMS
template. Until then, instantiating this class with non-None credentials
still only raises at send time — good enough for the factory pattern.
"""
from __future__ import annotations


class AliyunSmsProvider:
    def __init__(self, access_key: str, secret: str, template: str) -> None:
        self._access_key = access_key
        self._secret = secret
        self._template = template

    async def send(self, phone: str, code: str) -> None:
        raise NotImplementedError(
            "aliyun SMS integration lands in Plan 7 deployment phase — "
            "requires ICP filing + aliyun account + signed template"
        )
