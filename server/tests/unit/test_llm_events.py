"""app.llm.events: SSE wire serialization + cached content replay."""
from __future__ import annotations

import json
import pytest


def test_sse_pack_utf8_json_newlines():
    from app.llm.events import sse_pack
    out = sse_pack({"type": "delta", "text": "你好"})
    assert isinstance(out, bytes)
    assert out.startswith(b"data: ")
    assert out.endswith(b"\n\n")
    body = out[len(b"data: "):-2].decode("utf-8")
    assert json.loads(body) == {"type": "delta", "text": "你好"}


def test_sse_pack_compact_json_no_spaces():
    from app.llm.events import sse_pack
    out = sse_pack({"type": "done", "tokens_used": 0})
    assert b'"type":"done"' in out


@pytest.mark.asyncio
async def test_replay_cached_emits_model_deltas_done():
    from app.llm.events import replay_cached
    chunks = []
    async for raw in replay_cached("abcdefghij" * 5, "mimo-v2-pro",
                                   chunk_size=10, interval_ms=0):
        chunks.append(raw)
    import json as _json
    first = _json.loads(chunks[0][len(b"data: "):-2].decode())
    assert first == {"type": "model", "modelUsed": "cached", "source": "cache"}
    deltas = [c for c in chunks if b'"type":"delta"' in c]
    assert len(deltas) == 5
    last = _json.loads(chunks[-1][len(b"data: "):-2].decode())
    assert last["type"] == "done"
    assert last["source"] == "cache"
    assert last["tokens_used"] == 0
    assert last["full"] == "abcdefghij" * 5


@pytest.mark.asyncio
async def test_replay_cached_empty_content_still_emits_model_done():
    from app.llm.events import replay_cached
    chunks = []
    async for raw in replay_cached("", "mimo-v2-pro", chunk_size=10, interval_ms=0):
        chunks.append(raw)
    assert len(chunks) == 2
    assert b'"type":"model"' in chunks[0]
    assert b'"type":"done"' in chunks[1]
