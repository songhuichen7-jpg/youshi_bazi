from __future__ import annotations

from pathlib import Path


def test_expert_chat_token_cap_stays_readable_for_streaming_chat():
    source = Path("server/app/services/conversation_chat.py").read_text(encoding="utf-8")

    assert "max_tokens=4000" in source
    assert "max_tokens=9000" not in source
