"""Integration: conversations CRUD round-trip."""
from __future__ import annotations

import uuid

import pytest
from tests.integration.conftest import register_user


pytestmark = pytest.mark.asyncio


async def _register_with_chart(client) -> tuple[str, str]:
    """Returns (session_cookie, chart_id)."""
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie, _ = await register_user(client, phone)
    r = await client.post("/api/charts", cookies={"session": cookie}, json={
        "birth_input": {"year": 1990, "month": 5, "day": 12, "hour": 12, "gender": "male"},
    })
    assert r.status_code == 201, r.text
    return cookie, r.json()["chart"]["id"]


async def test_create_then_list_then_get(client):
    cookie, cid = await _register_with_chart(client)
    r = await client.post(f"/api/charts/{cid}/conversations",
                           cookies={"session": cookie}, json={"label": "工作"})
    assert r.status_code == 201
    conv = r.json()
    assert conv["label"] == "工作" and conv["position"] == 0

    r2 = await client.get(f"/api/charts/{cid}/conversations",
                           cookies={"session": cookie})
    assert r2.status_code == 200
    assert len(r2.json()["items"]) == 1

    r3 = await client.get(f"/api/conversations/{conv['id']}",
                           cookies={"session": cookie})
    assert r3.status_code == 200
    assert r3.json()["message_count"] == 0


async def test_create_default_label(client):
    cookie, cid = await _register_with_chart(client)
    r = await client.post(f"/api/charts/{cid}/conversations",
                           cookies={"session": cookie}, json={})
    assert r.status_code == 201
    assert r.json()["label"] == "对话 1"

    r2 = await client.post(f"/api/charts/{cid}/conversations",
                            cookies={"session": cookie}, json={})
    assert r2.json()["label"] == "对话 2"
    assert r2.json()["position"] == 1


async def test_patch_label(client):
    cookie, cid = await _register_with_chart(client)
    r = await client.post(f"/api/charts/{cid}/conversations",
                           cookies={"session": cookie}, json={})
    conv_id = r.json()["id"]
    r2 = await client.patch(f"/api/conversations/{conv_id}",
                             cookies={"session": cookie}, json={"label": "感情"})
    assert r2.status_code == 200
    assert r2.json()["label"] == "感情"


async def test_patch_label_blank_422(client):
    cookie, cid = await _register_with_chart(client)
    r = await client.post(f"/api/charts/{cid}/conversations",
                           cookies={"session": cookie}, json={})
    conv_id = r.json()["id"]
    r2 = await client.patch(f"/api/conversations/{conv_id}",
                             cookies={"session": cookie}, json={"label": "   "})
    assert r2.status_code == 422


async def test_delete_returns_204_and_hides_from_list(client):
    cookie, cid = await _register_with_chart(client)
    r = await client.post(f"/api/charts/{cid}/conversations",
                           cookies={"session": cookie}, json={})
    conv_id = r.json()["id"]
    rd = await client.delete(f"/api/conversations/{conv_id}",
                              cookies={"session": cookie})
    assert rd.status_code == 204
    rl = await client.get(f"/api/charts/{cid}/conversations",
                           cookies={"session": cookie})
    assert rl.json()["items"] == []
