"""WeChat JS-SDK ticket signing.

Caches access_token + jsapi_ticket for 7000s (slightly under WeChat's 7200s
hard limit to avoid boundary errors). Cache is module-level and per-process —
fine for single-worker dev; for multi-worker prod, move to Redis later.
"""
from __future__ import annotations

import hashlib
import secrets
import string
import time

import httpx
from fastapi import APIRouter, HTTPException, Query

import app.core.config as _config

router = APIRouter(prefix="/api/wx", tags=["wx"])

_CACHE: dict = {
    "access_token": None,
    "access_token_expiry": 0.0,
    "jsapi_ticket": None,
    "jsapi_ticket_expiry": 0.0,
}

_CACHE_TTL = 7000  # seconds, just under WeChat's 7200


async def _fetch_json(url: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.json()


async def _get_access_token() -> str:
    now = time.time()
    if _CACHE["access_token"] and now < _CACHE["access_token_expiry"]:
        return _CACHE["access_token"]
    settings = _config.settings
    if not settings.wx_app_id or not settings.wx_app_secret:
        raise HTTPException(500, "WX_APP_ID/WX_APP_SECRET not configured")
    url = (
        "https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential"
        f"&appid={settings.wx_app_id}&secret={settings.wx_app_secret}"
    )
    data = await _fetch_json(url)
    if "access_token" not in data:
        raise HTTPException(502, f"wx token error: {data}")
    _CACHE["access_token"] = data["access_token"]
    _CACHE["access_token_expiry"] = now + _CACHE_TTL
    return data["access_token"]


async def _get_jsapi_ticket() -> str:
    now = time.time()
    if _CACHE["jsapi_ticket"] and now < _CACHE["jsapi_ticket_expiry"]:
        return _CACHE["jsapi_ticket"]
    at = await _get_access_token()
    url = f"https://api.weixin.qq.com/cgi-bin/ticket/getticket?access_token={at}&type=jsapi"
    data = await _fetch_json(url)
    if data.get("errcode", 0) != 0 or "ticket" not in data:
        raise HTTPException(502, f"wx ticket error: {data}")
    _CACHE["jsapi_ticket"] = data["ticket"]
    _CACHE["jsapi_ticket_expiry"] = now + _CACHE_TTL
    return data["ticket"]


def _nonce(n: int = 16) -> str:
    alpha = string.ascii_letters + string.digits
    return "".join(secrets.choice(alpha) for _ in range(n))


@router.get("/jsapi-ticket")
async def get_jsapi_ticket(
    url: str = Query(..., description="current page full URL"),
) -> dict:
    ticket = await _get_jsapi_ticket()
    nonce = _nonce()
    timestamp = str(int(time.time()))
    raw = f"jsapi_ticket={ticket}&noncestr={nonce}&timestamp={timestamp}&url={url}"
    signature = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return {
        "appId": _config.settings.wx_app_id,
        "timestamp": timestamp,
        "nonceStr": nonce,
        "signature": signature,
    }
