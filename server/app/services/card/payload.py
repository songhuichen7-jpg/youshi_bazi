"""Pure-function card builder: BirthInput → CardResponse.

Integrates paipan排盘 + force/ge_ju analysis + mapping + JSON lookup
into a complete card payload. No IO, no DB.

Key paipan API facts (verified against source):
  - compute() takes keyword args directly (not a BirthInput object).
  - gender is a Literal['male', 'female'], not an enum.
  - hour=-1 signals unknown time; paipan sets hourUnknown=True.
  - Result has 'sizhu' dict with 'year'/'month'/'day'/'hour' GZ strings.
    The day stem is sizhu['day'][0] (first char of the two-char GZ string).
  - Result already contains 'force' and 'geJu' sub-dicts:
      force['sameRatio']                 — float in [0, 1]
      geJu['mainCandidate']['shishen']   — 十神 name string
"""
from __future__ import annotations

from paipan import compute as paipan_compute

from app.schemas.card import BirthInput, CardResponse
from app.services.card.loader import (
    FORMATIONS,
    SUBTAGS,
    TYPES,
    VERSION,
    illustration_url,
)
from app.services.card.mapping import (
    classify_state,
    extract_ge_ju_shi_shen,
    lookup_type_id,
)
from app.services.card.slug import generate_slug


def build_card_payload(birth: BirthInput, nickname: str | None) -> CardResponse:
    """Build a complete CardResponse from a BirthInput.

    Args:
        birth:    Validated birth data (our schema).
        nickname: Optional display name; passed through unchanged.

    Returns:
        A fully populated CardResponse ready for serialisation.
    """
    # 1. Run paipan. compute() takes keyword args; gender doesn't affect
    #    day_stem / force / ge_ju so we default to 'male'.
    #    hour=-1 is paipan's own sentinel for unknown time.
    kwargs: dict = dict(
        year=birth.year,
        month=birth.month,
        day=birth.day,
        hour=birth.hour,
        minute=birth.minute,
        gender="male",
    )
    if birth.city:
        kwargs["city"] = birth.city

    result = paipan_compute(**kwargs)

    # 2. Extract day stem from sizhu['day'] (first char of GZ string, e.g. '癸亥' → '癸')
    day_gz = result["sizhu"]["day"]
    if not day_gz:
        raise ValueError("paipan did not return a day GZ (sizhu.day is None/empty)")
    day_stem: str = day_gz[0]

    # 3. Force ratio → 绽放/蓄力 classification
    force = result["force"]
    same_ratio = float(force["sameRatio"])
    state, borderline = classify_state(same_ratio)

    # 4. 格局 → 十神 extraction
    ge_ju_result = result["geJu"]
    shi_shen = extract_ge_ju_shi_shen(ge_ju_result)

    # 5. 20-type lookup
    type_id = lookup_type_id(day_stem, state)
    info = TYPES[type_id]

    # 6. Formation data (state-aware suffix + golden_line)
    formation = FORMATIONS[shi_shen]

    # 7. Sub-tags (3 per cosmic_name × shi_shen combination)
    subtags = list(SUBTAGS[info["cosmic_name"]][shi_shen])

    # 8. Precision: 4-pillar when hour is known, 3-pillar otherwise
    precision = "4-pillar" if birth.hour >= 0 else "3-pillar"

    return CardResponse(
        type_id=type_id,
        cosmic_name=info["cosmic_name"],
        base_name=info["base_name"],
        state=state,
        state_icon="⚡" if state == "绽放" else "🔋",
        day_stem=day_stem,
        one_liner=info["one_liner"],
        ge_ju=shi_shen,
        suffix=formation["suffixes"][state],
        subtags=subtags,
        golden_line=formation["golden_lines"][state],
        personality_tag=info["personality_tag"],
        theme_color=info["theme_color"],
        card_bg=info["card_bg"],
        glow=info["glow"],
        illustration_url=illustration_url(info["illustration"]),
        reconstruction=info["reconstruction"],
        background_desc=info["background_desc"],
        precision=precision,
        borderline=borderline,
        share_slug=generate_slug(),
        nickname=nickname,
        version=VERSION,
    )
