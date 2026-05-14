"""GET /api/charts/{id}/classics — v2 cache shape (persona + verdict)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from tests.integration.conftest import register_user

pytestmark = pytest.mark.asyncio


_PERSONA_PAYLOAD = {
    "quote": "甲子日元，生于孟春。",
    "plain": "木火得位，五行中和。",
    "book": "滴天髓",
    "chapter": "性情",
    "section": "命例 1",
    "tier": "case",
    "fit_note": "日干甲、月令寅、建禄当令。",
}
_VERDICT_PAYLOAD = {
    "quote": "正官透干、印星护身者，主清贵",
    "book": "三命通会",
    "chapter": "论命格高低",
}


async def _register(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    return await register_user(client, phone)


async def _make_chart(client, cookie):
    body = {
        "birth_input": {"year": 1990, "month": 5, "day": 12, "hour": 12, "gender": "male"},
    }
    r = await client.post("/api/charts", cookies={"session": cookie}, json=body)
    assert r.status_code == 201, r.text
    return r.json()["chart"]["id"]


async def test_classics_v2_endpoint_returns_persona_and_verdict_shape(client):
    cookie, _ = await _register(client)
    chart_id = await _make_chart(client, cookie)

    fake_polish = AsyncMock(return_value={
        "persona": _PERSONA_PAYLOAD,
        "verdict": _VERDICT_PAYLOAD,
    })
    fake_retrieval = AsyncMock(return_value=[])

    with (
        patch("app.api.charts.retrieval_service.retrieve_for_chart", fake_retrieval),
        patch("app.api.charts.classics_polisher.polish_classics_for_chart", fake_polish),
    ):
        r = await client.get(
            f"/api/charts/{chart_id}/classics", cookies={"session": cookie},
        )

    assert r.status_code == 200
    body = r.json()
    assert body["persona"]["book"] == "滴天髓"
    assert body["persona"]["tier"] == "case"
    assert body["verdict"]["quote"].startswith("正官透干")
    assert "items" not in body  # 旧 shape 必须没了


async def test_classics_v2_cache_hit_skips_pipeline(client):
    cookie, _ = await _register(client)
    chart_id = await _make_chart(client, cookie)

    fake_polish = AsyncMock(return_value={
        "persona": _PERSONA_PAYLOAD, "verdict": _VERDICT_PAYLOAD,
    })
    fake_retrieval = AsyncMock(return_value=[])

    with (
        patch("app.api.charts.retrieval_service.retrieve_for_chart", fake_retrieval),
        patch("app.api.charts.classics_polisher.polish_classics_for_chart", fake_polish),
    ):
        # 第一次：跑 pipeline
        r1 = await client.get(
            f"/api/charts/{chart_id}/classics", cookies={"session": cookie},
        )
        assert r1.status_code == 200
        # 第二次：cache hit — polisher 不再被调
        polish_calls_before = fake_polish.call_count
        r2 = await client.get(
            f"/api/charts/{chart_id}/classics", cookies={"session": cookie},
        )
        assert r2.status_code == 200
        assert r2.json() == r1.json()
        assert fake_polish.call_count == polish_calls_before  # 没再调


async def test_classics_v2_does_not_cache_null_payload(client):
    """LLM 非确定性返 null 时不应缓存 — 下次请求重跑 pipeline 看能否拿到内容。"""
    cookie, _ = await _register(client)
    chart_id = await _make_chart(client, cookie)

    null_polish = AsyncMock(return_value={"persona": None, "verdict": None})
    fake_retrieval = AsyncMock(return_value=[])

    with (
        patch("app.api.charts.retrieval_service.retrieve_for_chart", fake_retrieval),
        patch("app.api.charts.classics_polisher.polish_classics_for_chart", null_polish),
    ):
        # 第一次：null payload, 不应写缓存
        r1 = await client.get(
            f"/api/charts/{chart_id}/classics", cookies={"session": cookie},
        )
        assert r1.status_code == 200
        assert r1.json() == {}  # exclude_none=True → empty dict
        polish_calls_after_r1 = null_polish.call_count
        # 第二次：cache miss (因为没缓存) — polish 再调一次
        r2 = await client.get(
            f"/api/charts/{chart_id}/classics", cookies={"session": cookie},
        )
        assert r2.status_code == 200
        assert null_polish.call_count == polish_calls_after_r1 + 1, \
            "null result should not have been cached, polish should run again"
