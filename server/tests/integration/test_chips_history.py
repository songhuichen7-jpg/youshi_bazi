"""Integration: chips endpoint accepts ?conversation_id and uses last 6 msgs."""
from __future__ import annotations

import os
import uuid
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.integration.conftest import register_user
from tests.integration.test_sse_helpers import consume_sse


pytestmark = pytest.mark.asyncio


async def _make_chart(client, cookie):
    body = {"birth_input": {"year": 1990, "month": 5, "day": 12, "hour": 12, "gender": "male"}}
    r = await client.post("/api/charts", cookies={"session": cookie}, json=body)
    return r.json()["chart"]["id"]


async def _seed_msgs(phone: str, conv_id: str, database_url: str):
    """Insert 8 messages (4 user/assistant pairs) directly via the service."""
    from app.core.crypto import decrypt_dek
    from app.db_types import user_dek_context
    from app.services import message as msg_svc

    engine = create_async_engine(database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        row = (await s.execute(
            text("SELECT dek_ciphertext FROM users WHERE phone=:p"),
            {"p": phone},
        )).first()
        kek = bytes.fromhex(os.environ["ENCRYPTION_KEK"])
        dek = decrypt_dek(row[0], kek)
        with user_dek_context(dek):
            import asyncio as _a
            for i in range(4):
                await msg_svc.insert(s, conversation_id=UUID(conv_id),
                                      role="user", content=f"u{i}")
                await s.commit()
                await _a.sleep(0.001)
                await msg_svc.insert(s, conversation_id=UUID(conv_id),
                                      role="assistant", content=f"a{i}")
                await s.commit()
                await _a.sleep(0.001)
    await engine.dispose()


async def test_chips_with_conversation_id_loads_history(client, monkeypatch, database_url):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie, _ = await register_user(client, phone)
    chart_id = await _make_chart(client, cookie)
    r = await client.post(f"/api/charts/{chart_id}/conversations",
                           cookies={"session": cookie}, json={})
    conv_id = r.json()["id"]

    # Seed 8 messages so only the last 6 should be picked up by recent_chat_history
    await _seed_msgs(phone, conv_id, str(database_url))

    # Capture the messages sent to the LLM
    captured: list[list[dict]] = []

    async def _capture_create(*, model, stream, messages, **kw):
        captured.append(messages)
        async def _gen():
            class _Chunk:
                def __init__(self, c):
                    self.choices = [SimpleNamespace(
                        delta=SimpleNamespace(content=c), finish_reason=None)]
                    self.usage = None
            class _Final:
                def __init__(self):
                    self.choices = [SimpleNamespace(
                        delta=SimpleNamespace(content=""), finish_reason="stop")]
                    self.usage = SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30)
            yield _Chunk('["Q1","Q2","Q3","Q4"]')
            yield _Final()
        return _gen()

    from app.llm import client as llm_client_mod
    monkeypatch.setattr(llm_client_mod._client.chat.completions, "create", _capture_create)

    # POST chips with conversation_id query param
    await consume_sse(client, f"/api/charts/{chart_id}/chips?conversation_id={conv_id}",
                       cookies={"session": cookie}, json_body={})

    assert len(captured) >= 1
    sent_messages = captured[0]
    # build_messages from prompts/chips puts history into the user message content
    user_content = sent_messages[-1]["content"]
    # Last 6 entries (chronological): u1, a1, u2, a2, u3, a3
    # u3 + a3 must appear; u0 must NOT appear (it's the 8th-most-recent)
    assert "u3" in user_content
    assert "a3" in user_content
    assert "u0" not in user_content
