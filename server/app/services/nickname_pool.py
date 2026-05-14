"""Server-side nickname pool — 50 二字文学风 names. Used to give every new
guest a meaningful default name (not '游客') and to back the
`/api/auth/me/reroll-nickname` endpoint.

Designed for collision tolerance: 50 entries, ~37% collision odds at
~10 concurrent guests is fine for an internal-beta product. cosmic_name
(deterministic from BaZi) + avatar color (hash of user_id) further
disambiguate same-nickname users in the UI.
"""
from __future__ import annotations

import random

NICKNAMES = [
    "林荫", "望舒", "听风", "知秋", "含露", "白鸥", "落花", "残荷",
    "听雪", "拾光", "云水", "星弦", "归朝", "无尘", "夜光", "朝雾",
    "寒山", "沧浪", "听筠", "微澜", "折枝", "半夏", "摘星", "觅渡",
    "抚琴", "拈花", "听蝉", "守拙", "归雁", "寄梅", "临风", "远岫",
    "浮岚", "凌波", "含光", "折桂", "知春", "寄云", "听潮", "抚松",
    "枕流", "钓月", "题霞", "数星", "借月", "守静", "归云", "醉墨",
    "含烟", "倚松",
]


def random_nickname(*, exclude: str | None = None) -> str:
    """Return a random pool name. If ``exclude`` is given, never return that
    value (used by reroll to avoid handing back the user's current name).
    Pool minus 1 entry is ~98% safe; if pool somehow empties (only when
    every entry is excluded — never happens with 50 entries and 1 exclusion),
    fall back to the first entry."""
    pool = NICKNAMES if exclude is None else [n for n in NICKNAMES if n != exclude]
    return random.choice(pool) if pool else NICKNAMES[0]
