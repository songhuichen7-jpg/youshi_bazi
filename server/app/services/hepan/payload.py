"""Compose a complete HepanResponse from two card sides + pair data.

Pure-function composer. No IO, no DB. Glues together:
  - 04a 55 base copy (pairs.json)
  - 04b 23 dynamic modifiers (dynamics.json)
  - mapping.classify() / state_pair_key() for category + modifier key

The composer is deterministic: same inputs → same output. The DB layer
caches the slug → both-sides snapshot but never the composed result
(which is cheap to recompute).
"""
from __future__ import annotations

from typing import Optional

from app.schemas.hepan import HepanResponse, HepanSide
from app.services.card.loader import TYPES, illustration_url
from app.services.hepan.loader import (
    DYNAMICS,
    DYNAMICS_VERSION,
    PAIRS_VERSION,
    find_pair,
)
from app.services.hepan.mapping import classify, state_pair_icon_key, state_pair_key


def _make_side(
    type_id: str,
    state: str,
    day_stem: str,
    nickname: Optional[str],
    role: str,
) -> HepanSide:
    info = TYPES[type_id]
    return HepanSide(
        type_id=type_id,
        cosmic_name=info["cosmic_name"],
        state=state,  # type: ignore[arg-type]
        state_icon="⚡" if state == "绽放" else "🔋",
        day_stem=day_stem,
        theme_color=info["theme_color"],
        card_bg=info["card_bg"],
        glow=info["glow"],
        illustration_url=illustration_url(info["illustration"]),
        nickname=nickname,
        role=role,
        # 透传 type_id 决定的静态字段, 让前端能把 HepanSide 当 card 直接渲染
        # 成 specimen 风格 (邀请落地页里 B 看到 A 的迷你卡)。
        personality_tag=info.get("personality_tag"),
        one_liner=info.get("one_liner"),
    )


def _blend_hex(c1: str, c2: str) -> str:
    """Average two hex colors '#RRGGBB' → blended hex.

    Used for the hepan card theme color — somewhere between A and B's
    天干 themes, lending the card its own identity instead of leaning
    on either side."""
    def to_rgb(h: str) -> tuple[int, int, int]:
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    r1, g1, b1 = to_rgb(c1)
    r2, g2, b2 = to_rgb(c2)
    return f"#{(r1 + r2) // 2:02X}{(g1 + g2) // 2:02X}{(b1 + b2) // 2:02X}"


def build_pending_payload(
    slug: str,
    a_type_id: str,
    a_state: str,
    a_day_stem: str,
    a_nickname: Optional[str],
) -> HepanResponse:
    """Build the payload returned right after A creates the invite (B not in yet)."""
    side_a = _make_side(a_type_id, a_state, a_day_stem, a_nickname, role="")
    return HepanResponse(
        slug=slug,
        status="pending",
        a=side_a,
        b=None,
        version=f"pairs={PAIRS_VERSION};dynamics={DYNAMICS_VERSION}",
    )


def build_completed_payload(
    slug: str,
    a_type_id: str,
    a_state: str,
    a_day_stem: str,
    a_nickname: Optional[str],
    b_type_id: str,
    b_state: str,
    b_day_stem: str,
    b_nickname: Optional[str],
) -> HepanResponse:
    """Build the full hepan reading with both sides + pair copy + modifier."""
    # 1. Determine relationship category + A 的方向 (giver/attacker/etc.)
    category, a_direction = classify(a_day_stem, b_day_stem)

    # 2. Look up base copy from 04a (preserves spec-authored direction)
    pair, swapped = find_pair(a_day_stem, b_day_stem)
    a_role = pair["b_role"] if swapped else pair["a_role"]
    b_role = pair["a_role"] if swapped else pair["b_role"]

    # 3. Pick dynamic modifier from 04b
    modifier_key = state_pair_key(a_state, b_state, category, a_direction)
    modifier = DYNAMICS["modifiers"][category].get(modifier_key)

    # 4. State pair icon ⚡⚡/⚡🔋/🔋⚡/🔋🔋 (always A→B directional)
    icon_key = state_pair_icon_key(a_state, b_state)
    state_pair = DYNAMICS["state_pair_icons"][icon_key]
    state_pair_label = DYNAMICS["state_pair_labels"][icon_key]

    # 5. Sides
    side_a = _make_side(a_type_id, a_state, a_day_stem, a_nickname, role=a_role)
    side_b = _make_side(b_type_id, b_state, b_day_stem, b_nickname, role=b_role)

    # 6. Blended pair theme
    pair_theme = _blend_hex(side_a.theme_color, side_b.theme_color)

    return HepanResponse(
        slug=slug,
        status="completed",
        a=side_a,
        b=side_b,
        category=category,
        label=pair["label"],
        subtags=list(pair["subtags"]),
        description=pair["description"],
        modifier=modifier,
        cta=pair["cta"],
        state_pair=state_pair,
        state_pair_label=state_pair_label,
        pair_theme_color=pair_theme,
        version=f"pairs={PAIRS_VERSION};dynamics={DYNAMICS_VERSION}",
    )
