"""Pydantic request/response schemas for the hepan (合盘) API."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.card import BirthInput, State


# ── Request bodies ──────────────────────────────────────────────────────

class HepanBirthInput(BirthInput):
    """Birth input for hepan.

    Card generation only needs 年/月/日/时; main-chat hepan context benefits from
    the fuller chart fields when the client has them. Existing invite/share
    callers may omit the added fields.
    """
    gender: Optional[Literal["male", "female"]] = None
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    ziConvention: Literal["early", "late"] = "early"
    useTrueSolarTime: bool = True


class HepanInviteRequest(BaseModel):
    """A creates an invitation. Logged-in creator flows also persist encrypted
    birth/paipan snapshots for main-chat relationship context."""
    birth: HepanBirthInput
    nickname: Optional[str] = Field(default=None, max_length=10)


class HepanCompleteRequest(BaseModel):
    """B opens the invitation link and submits their own birth + nickname."""
    birth: HepanBirthInput
    nickname: Optional[str] = Field(default=None, max_length=10)


# ── Per-side card snapshot ──────────────────────────────────────────────

class HepanSide(BaseModel):
    type_id: str
    cosmic_name: str
    state: State
    state_icon: str
    day_stem: str
    theme_color: str
    card_bg: str
    glow: str
    illustration_url: str
    nickname: Optional[str] = None
    role: str = ""  # 04a 的 A角色 / B角色
    # Live (not snapshotted) avatar URL JOINed from users.avatar_url. Always
    # None on the B side today — schema has no b_user_id linking the partner
    # back to a user account. None on A side too when the invite was created
    # anonymously (user_id IS NULL) or A hasn't uploaded an avatar.
    avatar_url: Optional[str] = None
    # 来自 TYPES[type_id] 的静态卡牌字段, 不是 PII。前端把 HepanSide 当 card
    # 渲染成迷你 specimen (e.g. 邀请落地页), 这两个能让 binomial / one_liner
    # 显出来, 不再是空架子。客户端 fallback 友好: 没传也能正常渲染。
    personality_tag: Optional[str] = None
    one_liner: Optional[str] = None


# ── Full hepan reading ──────────────────────────────────────────────────

Category = Literal[
    "天作搭子", "镜像搭子", "同频搭子", "滋养搭子", "火花搭子", "互补搭子"
]


class HepanResponse(BaseModel):
    slug: str
    status: Literal["pending", "completed"]

    # Sides — invitee may be None when status == "pending"
    a: HepanSide
    b: Optional[HepanSide] = None

    # Pair reading (only when completed)
    category: Optional[Category] = None
    label: Optional[str] = None
    subtags: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    modifier: Optional[str] = None  # 04b 动态修饰句
    cta: Optional[str] = None

    # State pair icon ⚡⚡/⚡🔋/🔋⚡/🔋🔋
    state_pair: Optional[str] = None
    state_pair_label: Optional[str] = None

    # Theme color for the hepan card — blended from both sides
    pair_theme_color: Optional[str] = None

    version: str = ""

    # 当前请求者是不是这条邀请的创建者（A）— 用 optional_user 注入；登录态
    # + user_id 匹配才 true。前端用这个决定是否展示 chat 区块 / "导出全文"
    # 按钮里的对话段。匿名 / B 一律 false。
    is_creator: bool = False


class HepanInviteResponse(BaseModel):
    """Returned from POST /api/hepan/invite — gives A back a slug + share link."""
    slug: str
    a: HepanSide
    invite_url: str  # e.g. /hepan/{slug}


# ── 我的合盘列表（GET /api/hepan/mine） ───────────────────────────────

class HepanMineItem(BaseModel):
    """单条合盘记录的列表展示。比 HepanResponse 轻 — 列表上不还原完整解读。"""
    slug: str
    status: Literal["pending", "completed"]
    a_nickname: Optional[str] = None
    b_nickname: Optional[str] = None
    a_cosmic_name: str
    b_cosmic_name: Optional[str] = None
    category: Optional[str] = None
    label: Optional[str] = None
    pair_theme_color: Optional[str] = None
    # Live (not snapshotted) avatar URLs JOINed from users.avatar_url. A side
    # uses HepanInvite.user_id → User; B side has no FK so b_avatar_url is
    # always None until schema gains b_user_id.
    a_avatar_url: Optional[str] = None
    b_avatar_url: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    share_count: int
    # True = 已经跑过完整解读 (reading_text 在缓存里)。Mine 列表 + 邀请弹窗
    # 历史用这个标"已读" / "未读" 区分。reading_generated_at 不直接暴露 —
    # bool 够 UI 用了，时间戳是后台分析数据。
    has_reading: bool = False
    # 这条邀请下的对话总数（user + assistant 都算）。Mine 行展示"X 轮对话"
    # 当大于 0；为 0 时不显示，避免给用户增加紧迫感。
    message_count: int = 0


class HepanMineResponse(BaseModel):
    items: list[HepanMineItem]


# ── Multi-turn chat (Plan 5+) ───────────────────────────────────────────

class HepanChatMessageRequest(BaseModel):
    """POST /api/hepan/{slug}/messages 的 body — 用户问的下一句话。"""
    message: str = Field(..., min_length=1, max_length=2000)


class HepanChatMessageItem(BaseModel):
    """聊天历史里的单条消息。content 已经在 service 层 from-bytes 解过密。"""
    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class HepanChatMessagesResponse(BaseModel):
    items: list[HepanChatMessageItem]
