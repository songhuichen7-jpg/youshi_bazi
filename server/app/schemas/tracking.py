"""Frontend event tracking schemas."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

TrackEvent = Literal[
    "page_view", "page_performance",
    "form_start", "form_submit", "form_error",
    "chart_create_success", "chart_create_failed", "result_view",
    "card_view", "card_save", "card_share",
    "hepan_invite_create", "hepan_view", "hepan_complete",
    "hepan_card_save", "hepan_text_export",
    "hepan_b_invite_create", "hepan_b_invite_copy", "hepan_b_view_chart",
    "report_view", "report_generate_success", "report_generate_failed",
    "chat_start", "chat_send", "chat_done", "chat_error",
    "quota_blocked", "paywall_view", "upgrade_click",
    "auth_register", "auth_login", "bind_phone", "logout",
    "pricing_view", "checkout_start",
    "cta_click",
]


class TrackProperties(BaseModel):
    """Known tracking properties. Extra fields are allowed and captured into `extra`."""
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type_id: Optional[str] = None
    channel: Optional[str] = None
    from_: Optional[str] = Field(default=None, alias="from")
    share_slug: Optional[str] = None
    anonymous_id: Optional[str] = None
    session_id: Optional[str] = None
    user_agent: Optional[str] = None
    viewport: Optional[str] = None
    page: Optional[str] = None
    route: Optional[str] = None
    search: Optional[str] = None
    load_ms: Optional[int] = Field(default=None, ge=0)
    ttfb_ms: Optional[int] = Field(default=None, ge=0)
    dom_interactive_ms: Optional[int] = Field(default=None, ge=0)
    transfer_size: Optional[int] = Field(default=None, ge=0)
    encoded_body_size: Optional[int] = Field(default=None, ge=0)
    image_transfer_size: Optional[int] = Field(default=None, ge=0)
    resource_count: Optional[int] = Field(default=None, ge=0)


class TrackRequest(BaseModel):
    event: TrackEvent
    properties: TrackProperties
