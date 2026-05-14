"""Plan 6: conversation/message/chat/gua schema validation."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.conversation import (
    ConversationCreateRequest,
    ConversationDetail,
    ConversationListResponse,
    ConversationPatchRequest,
)
from app.schemas.message import MessageDetail, MessagesListResponse
from app.schemas.chat import ChatMessageRequest
from app.schemas.gua import GuaCastRequest


def test_conversation_create_label_optional():
    body = ConversationCreateRequest()
    assert body.label is None
    body2 = ConversationCreateRequest(label="工作")
    assert body2.label == "工作"
    body3 = ConversationCreateRequest(label="   ")
    assert body3.label is None


def test_conversation_patch_label_required_nonempty():
    with pytest.raises(ValidationError):
        ConversationPatchRequest()
    with pytest.raises(ValidationError):
        ConversationPatchRequest(label="")
    with pytest.raises(ValidationError):
        ConversationPatchRequest(label="   ")
    body = ConversationPatchRequest(label="感情")
    assert body.label == "感情"


def test_conversation_detail_shape():
    now = datetime.now(tz=timezone.utc)
    d = ConversationDetail(
        id=uuid4(), chart_id=uuid4(), label="对话 1", position=0,
        created_at=now, updated_at=now,
        last_message_at=None, message_count=0,
        deleted_at=None,
    )
    j = d.model_dump(mode="json")
    assert set(j.keys()) >= {
        "id", "chart_id", "label", "position", "created_at", "updated_at",
        "last_message_at", "message_count", "deleted_at",
    }


def test_message_detail_role_enum_validates():
    now = datetime.now(tz=timezone.utc)
    for role in ("user", "assistant", "gua", "cta"):
        m = MessageDetail(id=uuid4(), role=role, content=None, meta=None, created_at=now)
        assert m.role == role
    with pytest.raises(ValidationError):
        MessageDetail(id=uuid4(), role="system", content=None, meta=None, created_at=now)


def test_messages_list_cursor_can_be_null():
    r = MessagesListResponse(items=[], next_cursor=None)
    assert r.next_cursor is None


def test_chat_message_request_strips_and_rejects_empty():
    body = ChatMessageRequest(message=" hello ")
    assert body.message == "hello"
    assert body.bypass_divination is False
    body2 = ChatMessageRequest(message="x", bypass_divination=True)
    assert body2.bypass_divination is True
    with pytest.raises(ValidationError):
        ChatMessageRequest(message="")
    with pytest.raises(ValidationError):
        ChatMessageRequest(message="   ")


def test_chat_message_request_accepts_client_context():
    body = ChatMessageRequest(
        message=" 上面第一条是什么意思 ",
        client_context={
            "view": "chart",
            "context_label": "戊午大运",
            "classics": [{"source": "穷通宝鉴", "quote": "七月甲木，丁火为尊。"}],
        },
    )

    assert body.message == "上面第一条是什么意思"
    assert body.client_context["view"] == "chart"
    assert body.client_context["classics"][0]["source"] == "穷通宝鉴"


def test_gua_cast_request_rejects_empty_question():
    body = GuaCastRequest(question="该不该换工作")
    assert body.question == "该不该换工作"
    with pytest.raises(ValidationError):
        GuaCastRequest(question="")
    with pytest.raises(ValidationError):
        GuaCastRequest(question="   ")
