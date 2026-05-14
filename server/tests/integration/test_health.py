"""Integration test: /api/health returns 200."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_returns_ok(async_client):
    r = await async_client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["env"] == "test"
    assert "version" in body
    assert body["llm"]["hasKey"] is False
    assert body["llm"]["model"]
