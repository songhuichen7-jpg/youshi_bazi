"""Pydantic request/response schemas for /api/auth/*.

Schemas are the HTTP-layer contract. They do NOT share fields with
``app/models/*`` (ORM). Fields like ``phone`` (raw) never appear in responses —
only ``phone_last4`` does.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ---- request bodies ---------------------------------------------------

SmsPurpose = Literal["register", "login", "bind"]


class SmsSendRequest(BaseModel):
    phone: str = Field(pattern=r"^\+?\d{11,15}$")
    purpose: SmsPurpose


class RegisterRequest(BaseModel):
    phone: str = Field(pattern=r"^\+?\d{11,15}$")
    code: str = Field(pattern=r"^\d{6}$")
    invite_code: str | None = Field(default=None, min_length=4, max_length=16)
    nickname: str | None = Field(default=None, max_length=40)
    agreed_to_terms: bool


class LoginRequest(BaseModel):
    phone: str = Field(pattern=r"^\+?\d{11,15}$")
    code: str = Field(pattern=r"^\d{6}$")


class GuestLoginRequest(BaseModel):
    """前端可选传入 guest_token（来自 localStorage）；后端按 token 找回
    已绑定的访客账号，否则创建一个新访客并把 token 存下来。"""
    guest_token: str | None = Field(default=None, max_length=64)


class ProfileUpdateRequest(BaseModel):
    """用户中心更名 / 改头像；onboarding modal 提交时也走这个端点。
    所有字段可选；都不传 = 不改。
    nickname 给空字符串 = 清掉。avatar_url 一般由 POST /api/auth/avatar
    上传后再 PATCH 进来；这里也允许直接传字符串（比如想清空，传 ""）。
    mark_onboarded=True 时 server 写 onboarded_at=now()——onboarding modal
    在用户提交完成或主动 dismiss 时都打这个标记。"""
    nickname: str | None = Field(default=None, max_length=40)
    avatar_url: str | None = Field(default=None, max_length=255)
    mark_onboarded: bool = False


class BindPhoneRequest(BaseModel):
    """访客升级 — 当前 session 的 user 加上手机号绑定，不新建账号。"""
    phone: str = Field(pattern=r"^\+?\d{11,15}$")
    code: str = Field(pattern=r"^\d{6}$")


class AccountDeleteRequest(BaseModel):
    # NOTE: must match literal — protects against accidental account loss.
    confirm: Literal["DELETE MY ACCOUNT"]


# ---- response bodies --------------------------------------------------


class SmsSendResponse(BaseModel):
    expires_in: int = 300
    # Dev-only field; only present when settings.env == "dev".
    # Using a double-underscore prefix so any accidental logger + toJSON
    # pass through obvious grep filters.
    devCode: str | None = Field(default=None, alias="__devCode")

    model_config = {"populate_by_name": True}


class UserResponse(BaseModel):
    id: UUID
    phone_last4: str
    nickname: str | None
    avatar_url: str | None = None
    role: Literal["user", "admin"]
    plan: Literal["lite", "standard", "pro"]
    plan_expires_at: datetime | None
    onboarded_at: datetime | None = None
    created_at: datetime


class MeResponse(BaseModel):
    user: UserResponse
    # Plan 3 returns {} placeholder; Plan 4 fills {kind: {used, limit, reset_at}}.
    quota_snapshot: dict = Field(default_factory=dict)


class SessionResponse(BaseModel):
    id: UUID
    user_agent: str | None
    ip: str | None
    created_at: datetime
    last_seen_at: datetime
    is_current: bool


class AccountDeleteResponse(BaseModel):
    shredded_at: datetime


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
