"""app.prompts.anchor: build_classical_anchor(retrieved)."""
from __future__ import annotations


def test_build_classical_anchor_empty_returns_empty():
    from app.prompts.anchor import build_classical_anchor
    assert build_classical_anchor([]) == ""


def test_build_classical_anchor_single_hit():
    from app.prompts.anchor import build_classical_anchor
    hits = [{"source":"穷通","scope":"full","chars":300,"text":"甲木参天，脱胎要火。"}]
    out = build_classical_anchor(hits)
    assert "穷通" in out
    assert "甲木参天" in out


def test_build_classical_anchor_uses_general_quote_guidance():
    from app.prompts.anchor import build_classical_anchor
    hits = [{"source":"三命","scope":"full","chars":20,"text":"财官须详。"}]
    out = build_classical_anchor(hits)

    assert "引用多少由本轮问题和原文质量决定" in out
    assert "优先参考排序靠前的锚点" in out
    assert "1-2" not in out
    assert "日柱+时柱" not in out
    assert "时上偏财" not in out


def test_build_classical_anchor_terse_shorter():
    from app.prompts.anchor import build_classical_anchor
    long_text = "食神制杀之格……" + ("详细释义" * 100)
    hits = [{"source":"三命","scope":"career","chars":len(long_text),"text":long_text}]
    full = build_classical_anchor(hits, terse=False)
    terse = build_classical_anchor(hits, terse=True)
    assert len(terse) <= len(full)


def test_build_classical_anchor_renders_claim_supported_label():
    """When retrieval2 selector tags hits with claim_supported, the prompt
    must show the (中文化的) sub-claim label so the LLM pairs the
    citation with the right analysis line."""
    from app.prompts.anchor import build_classical_anchor

    hits = [
        {
            "source": "穷通宝鉴", "scope": "正月",
            "chars": 18, "text": "正月甲木初春余寒,先丙后癸。",
            "claim_supported": "tiaohou",
        },
        {
            "source": "子平真诠", "scope": "论用神成败",
            "chars": 20, "text": "用神成则贵,败则贱。",
            "claim_supported": "main_geju",
        },
    ]
    out = build_classical_anchor(hits)
    assert "支持:调候(日干×月令)" in out
    assert "支持:主格局" in out
    # Header guidance for the new field is present
    assert "「支持:XX」" in out


def test_build_classical_anchor_no_supports_keeps_old_header():
    """Old callers / fallback paths leave claim_supported empty —
    rendering must stay backward-compatible."""
    from app.prompts.anchor import build_classical_anchor

    hits = [{"source": "穷通", "scope": "full", "chars": 9, "text": "脱胎要火。"}]
    out = build_classical_anchor(hits)
    assert "「支持:XX」" not in out  # extra guidance only when relevant
    assert "支持:" not in out
    assert "穷通" in out
