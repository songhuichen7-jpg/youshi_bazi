"""Dev SMS provider — logs only; does not actually send.

The code itself is NOT logged (structlog PII whitelist would drop it anyway,
but belt-and-suspenders). Dev-mode echo of the code into the HTTP response
body happens in api/auth.py, not here.
"""
from __future__ import annotations

import structlog

_log = structlog.get_logger(__name__)


class DevSmsProvider:
    async def send(self, phone: str, code: str) -> None:
        _log.info(
            "dev_sms_sent",
            # NOTE: do NOT log the raw code; only last 4 digits of phone for debug.
            phone_last4=phone[-4:],
            code_len=len(code),
        )
