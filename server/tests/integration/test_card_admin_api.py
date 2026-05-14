from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.asyncio
async def test_admin_metrics_requires_token(client):
    resp = await client.get("/api/admin/metrics")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_metrics_rejects_wrong_token(client, monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "admin_token", "realtoken")

    resp = await client.get("/api/admin/metrics", headers={"X-Admin-Token": "wrongtoken"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_metrics_returns_counts_and_rates(client, monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "admin_token", "testtoken")

    # Seed events
    for evt in ["card_view", "card_view", "card_view", "card_share", "form_submit"]:
        await client.post("/api/track", json={
            "event": evt, "properties": {"type_id": "01"},
        })

    resp = await client.get(
        "/api/admin/metrics",
        headers={"X-Admin-Token": "testtoken"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Counts
    assert data["counts"]["card_view"] >= 3
    assert data["counts"]["card_share"] >= 1
    assert data["counts"]["form_submit"] >= 1
    # Rates (relative to card_view)
    assert "share_rate" in data
    assert "form_submit_rate" in data


@pytest.mark.asyncio
async def test_admin_metrics_empty_views_returns_zero_rate(client, monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "admin_token", "testtoken")

    # No events sent — but other tests may have seeded events. Use a distant date window
    # to ensure we see 0 views (tests run quickly so "now - 1 year to now - 364 days" is safe).
    resp = await client.get(
        "/api/admin/metrics?from_=1990-01-01T00:00:00&to=1990-01-02T00:00:00",
        headers={"X-Admin-Token": "testtoken"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["share_rate"] == 0.0
    assert data["form_submit_rate"] == 0.0


@pytest.mark.asyncio
async def test_admin_overview_returns_anonymous_beta_metrics(client, monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "admin_token", "testtoken")
    suffix = uuid.uuid4().hex[:8]
    visitor_a = f"a_overview_{suffix}_1"
    visitor_b = f"a_overview_{suffix}_2"

    for event, visitor, props in [
        ("page_view", visitor_a, {"page": "landing", "route": "/"}),
        ("form_start", visitor_a, {}),
        ("form_submit", visitor_a, {}),
        ("chart_create_success", visitor_a, {"type_id": "08", "chart_id": str(uuid.uuid4())}),
        ("card_share", visitor_a, {"share_slug": "c_abc123"}),
        ("page_view", visitor_b, {"page": "hepan", "route": "/hepan/h_abc123"}),
        ("hepan_view", visitor_b, {"hepan_slug": "h_abc123"}),
        ("hepan_complete", visitor_b, {"hepan_slug": "h_abc123"}),
        ("chat_send", visitor_b, {"conversation_id": str(uuid.uuid4())}),
        ("chat_error", visitor_b, {"error_code": "LLM_TIMEOUT"}),
    ]:
        body = {
            "event": event,
            "properties": {
                "anonymous_id": visitor,
                "session_id": f"s_{visitor}",
                **props,
            },
        }
        resp = await client.post("/api/track", json=body)
        assert resp.status_code == 204, resp.text

    resp = await client.get(
        "/api/admin/overview",
        headers={"X-Admin-Token": "testtoken"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["totals"]["anonymous_visitors"] >= 2
    assert data["totals"]["sessions"] >= 2
    assert data["counts"]["chart_create_success"] >= 1
    assert data["counts"]["hepan_complete"] >= 1
    assert data["counts"]["chat_error"] >= 1
    assert data["rates"]["visit_to_chart"] > 0
    assert data["recent_events"]


@pytest.mark.asyncio
async def test_admin_visitors_groups_anonymous_activity(client, monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "admin_token", "testtoken")
    visitor = f"a_visitor_{uuid.uuid4().hex[:8]}"

    for event in ["page_view", "form_submit", "chart_create_success", "card_share"]:
        resp = await client.post("/api/track", json={
            "event": event,
            "properties": {
                "anonymous_id": visitor,
                "session_id": "s_grouped",
                "type_id": "05",
            },
        })
        assert resp.status_code == 204, resp.text

    resp = await client.get(
        f"/api/admin/visitors?anonymous_id={visitor}",
        headers={"X-Admin-Token": "testtoken"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["items"][0]["anonymous_id"] == visitor
    assert data["items"][0]["event_count"] == 4
    assert data["items"][0]["chart_count"] == 1
    assert data["items"][0]["share_count"] == 1


@pytest.mark.asyncio
async def test_admin_operations_returns_token_cost_and_funnel(client, database_url, monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "admin_token", "testtoken")

    engine = create_async_engine(database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        user_id = (await session.execute(
            text(
                """
                INSERT INTO users (phone, phone_last4, dek_ciphertext, dek_key_version)
                VALUES (:phone, :last4, :ct, 1)
                RETURNING id
                """
            ),
            {
                "phone": f"+86139{uuid.uuid4().int % 10**8:08d}",
                "last4": "7788",
                "ct": b"\x00" * 44,
            },
        )).scalar_one()
        other_user_id = (await session.execute(
            text(
                """
                INSERT INTO users (phone, phone_last4, dek_ciphertext, dek_key_version)
                VALUES (:phone, :last4, :ct, 1)
                RETURNING id
                """
            ),
            {
                "phone": f"+86137{uuid.uuid4().int % 10**8:08d}",
                "last4": "1122",
                "ct": b"\x00" * 44,
            },
        )).scalar_one()
        await session.execute(
            text(
                """
                INSERT INTO llm_usage_logs
                    (user_id, chart_id, endpoint, model, prompt_tokens,
                     completion_tokens, duration_ms, intent, error, created_at)
                VALUES
                    (:uid, NULL, 'chat:expert', 'mimo-v2-pro', 100, 50, 1000, NULL, NULL, now()),
                    (:uid, NULL, 'chat:expert', 'mimo-v2-pro', 300, 100, 3000, NULL, 'timeout', now()),
                    (:other_uid, NULL, 'gua', 'mimo-v2-flash', 40, 60, 500, NULL, NULL, now())
                """
            ),
            {"uid": user_id, "other_uid": other_user_id},
        )
        await session.commit()
    await engine.dispose()

    visitor = f"a_ops_{uuid.uuid4().hex[:8]}"
    for event in ["page_view", "form_start", "form_submit", "chart_create_success", "chat_send"]:
        resp = await client.post("/api/track", json={
            "event": event,
            "properties": {
                "anonymous_id": visitor,
                "session_id": "s_ops",
            },
        })
        assert resp.status_code == 204, resp.text

    for route, load_ms, ttfb_ms, transfer_size in [
        ("/", 1200, 180, 640_000),
        ("/app", 2600, 420, 1_120_000),
        ("/app", 1800, 260, 900_000),
    ]:
        resp = await client.post("/api/track", json={
            "event": "page_performance",
            "properties": {
                "anonymous_id": visitor,
                "session_id": "s_ops",
                "route": route,
                "page": "app" if route == "/app" else "landing",
                "load_ms": load_ms,
                "ttfb_ms": ttfb_ms,
                "transfer_size": transfer_size,
                "resource_count": 18,
            },
        })
        assert resp.status_code == 204, resp.text

    resp = await client.get(
        "/api/admin/operations",
        headers={"X-Admin-Token": "testtoken"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["tokens"]["total"] >= 650
    assert data["tokens"]["prompt"] >= 440
    assert data["tokens"]["completion"] >= 210
    assert data["tokens"]["calls"] >= 3
    assert data["tokens"]["avg_per_call"] > 0
    assert data["tokens"]["avg_per_active_user"] > 0
    assert data["tokens"]["p95_duration_ms"] >= 1000
    assert data["tokens"]["error_rate"] > 0
    assert any(row["endpoint"] == "chat:expert" and row["tokens"] >= 550 for row in data["endpoint_breakdown"])
    assert any(row["model"] == "mimo-v2-pro" for row in data["model_breakdown"])
    assert any(row["user_id"] == str(user_id) and row["tokens"] >= 550 for row in data["top_users"])
    assert data["funnel"][0]["key"] == "visit"
    assert any(step["key"] == "chart_success" and step["count"] >= 1 for step in data["funnel"])
    assert data["performance"]["samples"] >= 3
    assert data["performance"]["avg_load_ms"] > 0
    assert data["performance"]["p95_load_ms"] >= 1800
    assert data["performance"]["avg_ttfb_ms"] > 0
    assert data["performance"]["total_transfer_kb"] > 0
    assert data["performance_series"]
    assert any(row["route"] == "/app" and row["samples"] >= 2 for row in data["route_performance"])
