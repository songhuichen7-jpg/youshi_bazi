"""Unit tests for sms provider factory + Dev stub + Aliyun skeleton."""
from __future__ import annotations

import pytest


def test_factory_returns_dev_when_aliyun_key_missing(monkeypatch):
    """Default test env has no aliyun_sms_* settings → DevSmsProvider."""
    # Clear factory cache so monkeypatching is honored.
    from app.sms import get_sms_provider, DevSmsProvider
    get_sms_provider.cache_clear()

    # Factory reads the `settings` name bound inside app.sms at import time.
    # The conftest autouse fixture reloads app.core.config between tests, which
    # can desync app.sms.settings from app.core.config.settings — so patch the
    # name the factory actually reads.
    monkeypatch.setattr("app.sms.settings.aliyun_sms_access_key", None)
    monkeypatch.setattr("app.sms.settings.aliyun_sms_secret", None)
    monkeypatch.setattr("app.sms.settings.aliyun_sms_template", None)

    p = get_sms_provider()
    assert isinstance(p, DevSmsProvider)

    # Clear cache for subsequent tests
    get_sms_provider.cache_clear()


def test_factory_returns_aliyun_when_all_keys_set(monkeypatch):
    from app.sms import get_sms_provider, AliyunSmsProvider
    get_sms_provider.cache_clear()

    monkeypatch.setattr("app.sms.settings.aliyun_sms_access_key", "AK123")
    monkeypatch.setattr("app.sms.settings.aliyun_sms_secret", "secret")
    monkeypatch.setattr("app.sms.settings.aliyun_sms_template", "SMS_123")

    p = get_sms_provider()
    assert isinstance(p, AliyunSmsProvider)

    get_sms_provider.cache_clear()


@pytest.mark.asyncio
async def test_dev_provider_does_not_send(caplog):
    """DevSmsProvider.send should only log, not raise; code is NOT in the log."""
    import logging
    from app.sms import DevSmsProvider

    with caplog.at_level(logging.INFO):
        p = DevSmsProvider()
        await p.send("+8613800001234", "654321")

    # The raw code should not appear anywhere in the log output.
    for record in caplog.records:
        assert "654321" not in record.getMessage()


@pytest.mark.asyncio
async def test_aliyun_skeleton_raises_not_implemented():
    from app.sms import AliyunSmsProvider

    p = AliyunSmsProvider(access_key="AK", secret="S", template="T")
    with pytest.raises(NotImplementedError, match="Plan 7"):
        await p.send("+8613800001234", "654321")
