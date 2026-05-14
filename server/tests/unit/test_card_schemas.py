from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.card import BirthInput, CardRequest, CardResponse


def test_birth_input_accepts_hour_minus_one_for_unknown():
    b = BirthInput(year=1998, month=7, day=15, hour=-1, minute=0)
    assert b.hour == -1


def test_birth_input_rejects_year_out_of_range():
    with pytest.raises(ValidationError):
        BirthInput(year=1800, month=1, day=1, hour=-1, minute=0)


def test_birth_input_rejects_invalid_month():
    with pytest.raises(ValidationError):
        BirthInput(year=1998, month=13, day=1, hour=-1, minute=0)


def test_birth_input_rejects_hour_24():
    with pytest.raises(ValidationError):
        BirthInput(year=1998, month=7, day=15, hour=24, minute=0)


# ── 复合日历日合法性 ─────────────────────────────────────────────────
# 字段级 ge/le 只能保证 day∈[1,31]、month∈[1,12]，组合却可能非法日
# (2025-02-29 / 2024-04-31)。以前会沿到 paipan.compute → datetime() 抛
# ValueError → FastAPI 返 500。BirthInput 的 model_validator 现在拦下，
# 转 ValidationError → 422。
def test_birth_input_rejects_feb_29_in_non_leap_year():
    with pytest.raises(ValidationError) as excinfo:
        BirthInput(year=2025, month=2, day=29, hour=12, minute=0)
    assert "invalid date" in str(excinfo.value)


def test_birth_input_accepts_feb_29_in_leap_year():
    b = BirthInput(year=2024, month=2, day=29, hour=12, minute=0)
    assert b.day == 29


def test_birth_input_rejects_april_31():
    with pytest.raises(ValidationError):
        BirthInput(year=2024, month=4, day=31, hour=12, minute=0)


def test_birth_input_rejects_feb_30():
    with pytest.raises(ValidationError):
        BirthInput(year=2024, month=2, day=30, hour=12, minute=0)


def test_birth_input_accepts_hour_unknown_with_invalid_date_still_rejects():
    # hour=-1 (时辰未知) 不能绕过日期校验 — 校验是模型级，独立于 hour 字段
    with pytest.raises(ValidationError):
        BirthInput(year=2025, month=2, day=29, hour=-1, minute=0)


def test_card_request_nickname_optional_and_length_capped():
    r = CardRequest(birth=BirthInput(year=1998, month=7, day=15, hour=14, minute=0))
    assert r.nickname is None
    with pytest.raises(ValidationError):
        CardRequest(
            birth=BirthInput(year=1998, month=7, day=15, hour=14, minute=0),
            nickname="x" * 11,
        )


def test_card_request_strips_html_from_nickname():
    r = CardRequest(
        birth=BirthInput(year=1998, month=7, day=15, hour=14, minute=0),
        nickname="<script>小满</script>",
    )
    assert r.nickname == "小满"


def test_card_response_all_required_fields_present():
    resp = CardResponse(
        type_id="01",
        cosmic_name="春笋",
        base_name="参天木命",
        state="绽放",
        state_icon="⚡",
        day_stem="甲",
        one_liner="越压越往上长",
        ge_ju="食神",
        suffix="天生享乐家",
        subtags=["冲上去再说", "人缘自己来", "会吃会玩也会赚"],
        golden_line="我不卷，但我什么都不缺",
        personality_tag="参天型",
        theme_color="#2D6A4F",
        card_bg="#1a3a2a",
        glow="#4dcc7a",
        illustration_url="/static/cards/illustrations/01-chunsun.png",
        reconstruction="这不是倔，是我的根扎得够深，压不弯。",
        background_desc="你是参天大木。向上生长是本能，被压得越深，根扎得越牢。",
        precision="4-pillar",
        borderline=False,
        share_slug="c_a9f3b2k1xx",
        nickname="小满",
        version="v4.0-2026-04",
    )
    assert resp.type_id == "01"
