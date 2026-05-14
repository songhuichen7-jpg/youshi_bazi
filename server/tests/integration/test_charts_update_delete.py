"""PATCH + DELETE /api/charts/:id integration tests."""
from __future__ import annotations

import uuid

import pytest
from tests.integration.conftest import register_user


async def _register(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    return await register_user(client, phone)


async def _make(client, cookie, label=None):
    body = {
        "birth_input": {"year": 1990, "month": 5, "day": 12, "hour": 12, "gender": "male"},
    }
    if label is not None:
        body["label"] = label
    r = await client.post("/api/charts", cookies={"session": cookie}, json=body)
    return r.json()["chart"]["id"]


@pytest.mark.asyncio
async def test_patch_label_happy(client):
    cookie, _ = await _register(client)
    cid = await _make(client, cookie, "old")
    r = await client.patch(
        f"/api/charts/{cid}",
        cookies={"session": cookie},
        json={"label": "new"},
    )
    assert r.status_code == 200
    assert r.json()["chart"]["label"] == "new"


@pytest.mark.asyncio
async def test_patch_label_to_null(client):
    cookie, _ = await _register(client)
    cid = await _make(client, cookie, "anything")
    r = await client.patch(
        f"/api/charts/{cid}",
        cookies={"session": cookie},
        json={"label": None},
    )
    assert r.status_code == 200
    assert r.json()["chart"]["label"] is None


@pytest.mark.asyncio
async def test_patch_label_too_long_422(client):
    cookie, _ = await _register(client)
    cid = await _make(client, cookie)
    r = await client.patch(
        f"/api/charts/{cid}",
        cookies={"session": cookie},
        json={"label": "a" * 41},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_nonexistent_404(client):
    cookie, _ = await _register(client)
    r = await client.patch(
        f"/api/charts/{uuid.uuid4()}",
        cookies={"session": cookie},
        json={"label": "x"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_patch_cross_user_404(client):
    cookie_a, _ = await _register(client)
    cookie_b, _ = await _register(client)
    cid = await _make(client, cookie_a, "a")
    r = await client.patch(
        f"/api/charts/{cid}",
        cookies={"session": cookie_b},
        json={"label": "evil"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_happy(client):
    cookie, _ = await _register(client)
    cid = await _make(client, cookie)
    r = await client.delete(f"/api/charts/{cid}", cookies={"session": cookie})
    assert r.status_code == 204
    r = await client.get(f"/api/charts/{cid}", cookies={"session": cookie})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_already_soft_deleted_409(client):
    cookie, _ = await _register(client)
    cid = await _make(client, cookie)
    r = await client.delete(f"/api/charts/{cid}", cookies={"session": cookie})
    assert r.status_code == 204
    r = await client.delete(f"/api/charts/{cid}", cookies={"session": cookie})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "CHART_ALREADY_DELETED"


@pytest.mark.asyncio
async def test_delete_cross_user_404(client):
    cookie_a, _ = await _register(client)
    cookie_b, _ = await _register(client)
    cid = await _make(client, cookie_a)
    r = await client.delete(f"/api/charts/{cid}", cookies={"session": cookie_b})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_404(client):
    cookie, _ = await _register(client)
    r = await client.delete(f"/api/charts/{uuid.uuid4()}", cookies={"session": cookie})
    assert r.status_code == 404
