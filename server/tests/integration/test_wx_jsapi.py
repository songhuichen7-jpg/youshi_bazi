from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_jsapi_ticket_returns_signature_payload(client, monkeypatch):
    import app.core.config as _config
    monkeypatch.setattr(_config.settings, "wx_app_id", "wxtestappid")
    monkeypatch.setattr(_config.settings, "wx_app_secret", "testsecret")

    # Clear module-level cache to avoid cross-test pollution
    from app.api import wx as wx_mod
    wx_mod._CACHE.update({
        "access_token": None, "access_token_expiry": 0.0,
        "jsapi_ticket": None, "jsapi_ticket_expiry": 0.0,
    })

    fake_access_token = {"access_token": "AT_ABC", "expires_in": 7200}
    fake_ticket = {"ticket": "TK_XYZ", "expires_in": 7200, "errcode": 0}

    with patch("app.api.wx._fetch_json", new=AsyncMock(side_effect=[
        fake_access_token, fake_ticket,
    ])):
        resp = await client.get(
            "/api/wx/jsapi-ticket?url=https%3A%2F%2Fyoushi.app%2Fcard%2Fc_abc"
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["appId"] == "wxtestappid"
    assert "signature" in data
    assert "timestamp" in data
    assert "nonceStr" in data
    assert len(data["signature"]) == 40  # sha1 hex


@pytest.mark.asyncio
async def test_jsapi_ticket_500_when_not_configured(client, monkeypatch):
    import app.core.config as _config
    monkeypatch.setattr(_config.settings, "wx_app_id", "")
    monkeypatch.setattr(_config.settings, "wx_app_secret", "")

    from app.api import wx as wx_mod
    wx_mod._CACHE.update({
        "access_token": None, "access_token_expiry": 0.0,
        "jsapi_ticket": None, "jsapi_ticket_expiry": 0.0,
    })

    resp = await client.get("/api/wx/jsapi-ticket?url=https%3A%2F%2Fyoushi.app")
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_jsapi_ticket_signature_is_deterministic_for_same_inputs(client, monkeypatch):
    """If access_token/ticket are cached and url+timestamp+nonce are known,
    signature is sha1(jsapi_ticket={t}&noncestr={n}&timestamp={ts}&url={u})."""
    import hashlib
    import app.core.config as _config
    monkeypatch.setattr(_config.settings, "wx_app_id", "wxapp")
    monkeypatch.setattr(_config.settings, "wx_app_secret", "secret")

    from app.api import wx as wx_mod
    # Warm cache
    wx_mod._CACHE["access_token"] = "AT_CACHED"
    wx_mod._CACHE["access_token_expiry"] = 9999999999.0
    wx_mod._CACHE["jsapi_ticket"] = "TK_FIXED"
    wx_mod._CACHE["jsapi_ticket_expiry"] = 9999999999.0

    resp = await client.get("/api/wx/jsapi-ticket?url=https%3A%2F%2Fx.com")
    assert resp.status_code == 200
    data = resp.json()
    expected = hashlib.sha1(
        f"jsapi_ticket=TK_FIXED&noncestr={data['nonceStr']}"
        f"&timestamp={data['timestamp']}&url=https://x.com".encode()
    ).hexdigest()
    assert data["signature"] == expected
