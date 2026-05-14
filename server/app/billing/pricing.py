"""Plan + period pricing.

价格用 cents (integer) 存，避免浮点误差；展示时 / 100 即 ¥X.XX。
年付通常 = 10 × monthly（送 2 个月）— 这是常见做法但可调。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal


Plan = Literal["standard", "pro"]
Period = Literal["monthly", "annual"]


PRICING: dict[Plan, dict[Period, int]] = {
    "standard": {"monthly": 1900,  "annual": 19000},   # ¥19 / ¥190
    "pro":      {"monthly": 6900,  "annual": 69000},   # ¥69 / ¥690
}


def price_cents(plan: Plan, period: Period) -> int:
    return PRICING[plan][period]


def period_end(period: Period, *, starts_at: datetime | None = None) -> datetime:
    """Calculate ``ends_at`` from a period+start. 月付 = +30 天，年付 = +365 天。
    跨月不严格按自然月，简化对账（财务里通常按"30 天 / 365 天"算量）。"""
    base = starts_at or datetime.now(tz=timezone.utc)
    days = 30 if period == "monthly" else 365
    return base + timedelta(days=days)


def display_price(plan: Plan, period: Period) -> str:
    """渲染给用户看的价格字符串，例如 '¥19'。"""
    cents = price_cents(plan, period)
    yuan = cents // 100
    cents_part = cents % 100
    if cents_part == 0:
        return f"¥{yuan}"
    return f"¥{yuan}.{cents_part:02d}"
