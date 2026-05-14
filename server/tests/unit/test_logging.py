"""Unit tests for app.core.logging PII scrub."""
from __future__ import annotations


def test_scrub_drops_nonwhitelist_keys():
    from app.core.logging import _pii_scrub_processor

    out = _pii_scrub_processor(
        None, "info",
        {"event": "hi", "user_id": "u1", "phone": "138****", "password": "x"},
    )
    assert "event" in out
    assert "user_id" in out
    assert "phone" not in out
    assert "password" not in out


def test_scrub_keeps_all_whitelisted_keys():
    from app.core.logging import _pii_scrub_processor, _LOG_WHITELIST

    event = {k: "x" for k in _LOG_WHITELIST}
    out = _pii_scrub_processor(None, "info", dict(event))
    assert set(out.keys()) == _LOG_WHITELIST
