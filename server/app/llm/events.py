"""SSE wire format helpers — single `data:` channel + JSON type-tagged events.

Wire format chosen to match MVP Node server for frontend compat:
    data: {"type":"model","modelUsed":"..."}\n\n
    data: {"type":"delta","text":"..."}\n\n
    data: {"type":"done","full":"...","tokens_used":N}\n\n
    data: {"type":"error","code":"...","message":"..."}\n\n

Cache replay additionally sets source: 'cache' on model/done events.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator


def sse_pack(obj: dict) -> bytes:
    """Serialize a single SSE event.

    Uses compact JSON (no spaces) to minimize bytes on the wire. UTF-8 encoded.
    """
    return ("data: " + json.dumps(obj, ensure_ascii=False, separators=(",", ":")) +
            "\n\n").encode("utf-8")


async def replay_cached(
    content: str,
    model_used_orig: str | None,
    *,
    chunk_size: int = 30,
    interval_ms: int = 20,
) -> AsyncIterator[bytes]:
    """Replay cached content as SSE events — model → delta × N → done.

    NOTE: spec §4.2 — 30 chars / 20ms ≈ 1500 chars/sec keeps typing effect.
    model_used_orig is informational only; cache events always advertise
    modelUsed='cached' + source='cache' so the frontend can tell it's a replay.
    """
    yield sse_pack({"type": "model", "modelUsed": "cached", "source": "cache"})
    safe_content = content or ""
    for i in range(0, len(safe_content), chunk_size):
        chunk = safe_content[i:i + chunk_size]
        yield sse_pack({"type": "delta", "text": chunk})
        if interval_ms > 0:
            await asyncio.sleep(interval_ms / 1000.0)
    yield sse_pack({
        "type": "done",
        "full": safe_content,
        "tokens_used": 0,
        "source": "cache",
    })
