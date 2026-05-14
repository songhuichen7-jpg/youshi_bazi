"""Integration: cross-user 404 on every conversation/message route."""
from __future__ import annotations

import uuid

import pytest
from tests.integration.conftest import register_user


pytestmark = pytest.mark.asyncio


async def _register_with_chart(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie, _ = await register_user(client, phone)
    r = await client.post("/api/charts", cookies={"session": cookie}, json={
        "birth_input": {"year": 1990, "month": 5, "day": 12, "hour": 12, "gender": "male"},
    })
    return cookie, r.json()["chart"]["id"]


async def _register_second_user(client):
    phone = f"+86139{uuid.uuid4().int % 10**8:08d}"
    cookie, _ = await register_user(client, phone)
    return cookie


async def test_cross_user_get_404(client):
    cookie_a, cid = await _register_with_chart(client)
    cookie_b = await _register_second_user(client)
    r = await client.post(f"/api/charts/{cid}/conversations",
                           cookies={"session": cookie_a}, json={})
    conv_id = r.json()["id"]
    r2 = await client.get(f"/api/conversations/{conv_id}",
                           cookies={"session": cookie_b})
    assert r2.status_code == 404


async def test_cross_user_patch_404(client):
    cookie_a, cid = await _register_with_chart(client)
    cookie_b = await _register_second_user(client)
    r = await client.post(f"/api/charts/{cid}/conversations",
                           cookies={"session": cookie_a}, json={})
    conv_id = r.json()["id"]
    r2 = await client.patch(f"/api/conversations/{conv_id}",
                             cookies={"session": cookie_b}, json={"label": "x"})
    assert r2.status_code == 404


async def test_cross_user_delete_404(client):
    cookie_a, cid = await _register_with_chart(client)
    cookie_b = await _register_second_user(client)
    r = await client.post(f"/api/charts/{cid}/conversations",
                           cookies={"session": cookie_a}, json={})
    conv_id = r.json()["id"]
    r2 = await client.delete(f"/api/conversations/{conv_id}",
                              cookies={"session": cookie_b})
    assert r2.status_code == 404


async def test_cross_user_messages_404(client):
    cookie_a, cid = await _register_with_chart(client)
    cookie_b = await _register_second_user(client)
    r = await client.post(f"/api/charts/{cid}/conversations",
                           cookies={"session": cookie_a}, json={})
    conv_id = r.json()["id"]
    r2 = await client.get(f"/api/conversations/{conv_id}/messages",
                           cookies={"session": cookie_b})
    assert r2.status_code == 404
