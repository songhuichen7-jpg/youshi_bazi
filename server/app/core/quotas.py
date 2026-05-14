"""Quota limits per plan + timezone helpers for daily-reset quotas.

Plans (Plan 5+ membership design):
  - lite      默认免费档：能完整体验产品，但日用量受限。
  - standard  常用付费档：5× lite 的对话量 + 5 张命盘。
  - pro       重度档：20× lite。

老 ``free`` 留作 alias 指向 lite — 防止迁移没跑过的环境查 QUOTAS 时 KeyError。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_BEIJING = ZoneInfo("Asia/Shanghai")


# 单位：每用户每日（北京日界）的次数上限。
# 保持各 kind 的语义和老版本一致，只是数值随档位放大。
QUOTAS: dict[str, dict[str, int]] = {
    "lite": {
        "sms_send":       20,   # 防短信轰炸；档位无关，三档都是 20
        "chat_message":   30,
        "section_regen":   5,
        "verdicts_regen":  3,
        "dayun_regen":    10,
        "liunian_regen":  10,
        "gua":             3,
    },
    "standard": {
        "sms_send":       20,
        "chat_message":  150,   # 5× lite
        "section_regen":  15,
        "verdicts_regen": 10,
        "dayun_regen":    30,
        "liunian_regen":  30,
        "gua":            15,   # 5× lite
    },
    "pro": {
        "sms_send":       20,
        "chat_message":  600,   # 20× lite
        "section_regen":  50,
        "verdicts_regen": 30,
        "dayun_regen":   100,
        "liunian_regen": 100,
        "gua":            60,   # 20× lite
    },
}
# Backward-compat — 0008 之前的 DB / 测试夹具里 plan='free' 的行还在调
# QUOTAS[user.plan] 时不要 KeyError；语义等价于 lite。
QUOTAS["free"] = QUOTAS["lite"]


# 累计型上限（不是日重置）：用户在该档位下最多能持有多少张活动命盘。
# 软删的命盘不计入。
CHART_MAX_BY_PLAN: dict[str, int] = {
    "lite":     2,
    "standard": 5,
    "pro":     20,
    "free":     2,    # backward-compat alias
}


def chart_max_for(plan: str) -> int:
    """档位对应的命盘上限；未知档位兜底到 lite 的 2，以免越权。"""
    return CHART_MAX_BY_PLAN.get(plan, CHART_MAX_BY_PLAN["lite"])


# 老导入兼容：原来全局 15 张被调用方当作"硬上限"；新版本里"硬上限"应改成
# 按 user.plan 查 chart_max_for(...)。这里保留常量但语义改为"匿名 / 默认 lite
# 档位的展示上限"，比如 /api/config 在没有 user 上下文时拿这个数。
MAX_CHARTS_PER_USER = CHART_MAX_BY_PLAN["lite"]


def today_beijing() -> str:
    """YYYY-MM-DD string in Asia/Shanghai (quota reset boundary)."""
    return datetime.now(tz=_BEIJING).strftime("%Y-%m-%d")


def next_midnight_beijing() -> datetime:
    """Next 00:00:00 in Asia/Shanghai (when quota resets)."""
    now = datetime.now(tz=_BEIJING)
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    return tomorrow


def seconds_until_midnight() -> int:
    """Seconds from now until the next Beijing midnight."""
    now = datetime.now(tz=_BEIJING)
    return int((next_midnight_beijing() - now).total_seconds())
