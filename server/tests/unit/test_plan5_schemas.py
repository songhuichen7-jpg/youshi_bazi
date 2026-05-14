"""Plan 5 schemas + UpstreamLLMError smoke tests."""
from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_section_body_accepts_all_7_sections():
    from app.schemas.llm import SectionBody
    for s in ("career","personality","wealth","relationship","health","appearance","special"):
        b = SectionBody(section=s)
        assert b.section == s


def test_section_body_rejects_unknown():
    from app.schemas.llm import SectionBody
    with pytest.raises(ValidationError):
        SectionBody(section="unknown")


def test_liunian_body_happy():
    from app.schemas.llm import LiunianBody
    b = LiunianBody(dayun_index=3, year_index=7)
    assert b.dayun_index == 3 and b.year_index == 7


def test_liunian_body_rejects_negative():
    from app.schemas.llm import LiunianBody
    with pytest.raises(ValidationError):
        LiunianBody(dayun_index=-1, year_index=0)
    with pytest.raises(ValidationError):
        LiunianBody(dayun_index=0, year_index=-1)


def test_quota_kind_usage_shape():
    from app.schemas.quota import QuotaKindUsage
    from datetime import datetime, timezone
    u = QuotaKindUsage(used=3, limit=30, resets_at=datetime.now(tz=timezone.utc))
    assert u.used == 3 and u.limit == 30


def test_quota_response_accepts_all_7_kinds():
    # NOTE: migration 0008 / schemas/quota.py — plan 是 {lite, standard, pro}，
    # 旧名 "free" 在 0010 已经从 DB CHECK 移除。
    from app.schemas.quota import QuotaResponse, QuotaKindUsage
    from datetime import datetime, timezone
    now = datetime.now(tz=timezone.utc)
    kinds = ("chat_message","section_regen","verdicts_regen",
             "dayun_regen","liunian_regen","gua","sms_send")
    usage = {k: QuotaKindUsage(used=0, limit=1, resets_at=now) for k in kinds}
    r = QuotaResponse(plan="lite", usage=usage)
    assert set(r.usage.keys()) == set(kinds)


def test_upstream_llm_error_codes():
    from app.services.exceptions import UpstreamLLMError
    e1 = UpstreamLLMError(code="UPSTREAM_LLM_FAILED", message="primary down")
    assert e1.code == "UPSTREAM_LLM_FAILED" and e1.message == "primary down"
    e2 = UpstreamLLMError(code="UPSTREAM_LLM_TIMEOUT", message="no delta")
    assert e2.code == "UPSTREAM_LLM_TIMEOUT"
