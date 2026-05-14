"""Core unit tests for retrieval2.

Compact and focused — tokenizer, splitter, BM25, KG, intents, selector
parsing, service round-trip — all mocked LLM where needed.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.retrieval2 import (
    QueryIntent,
    bazi_chart_to_intents,
    book_label,
    build_bm25,
    build_kg,
    canonical,
    encode,
    encode_query,
    expand,
    iter_classics,
    load_bm25,
    normalize,
    save_bm25,
    split_chapter,
)
from app.retrieval2.tagger import VOCAB, parse_response
from app.retrieval2.selector import Candidate, parse_picks, select as selector_select
from app.retrieval2.types import ClaimTags, ClaimUnit
from app.retrieval2 import service, storage

REPO_ROOT = Path(__file__).resolve().parents[4]
CLASSICS = REPO_ROOT / "classics"


# ── normalize / synonyms ───────────────────────────────────────────────────


def test_variant_char_fold():
    assert normalize("七煞") == "七杀"


def test_synonym_expansion_煞_to_杀():
    cls = expand("煞")
    assert "杀" in cls


def test_canonical_form():
    assert canonical("煞") == "七杀"
    assert canonical("身轻") == "身弱"


def test_book_label_mapping():
    assert book_label("ziping-zhenquan") == "子平真诠"


# ── tokenizer ──────────────────────────────────────────────────────────────


def test_tokenizer_emits_ngrams_and_synonyms():
    toks = set(encode("七煞重身"))
    assert "煞" not in toks  # variant-folded
    assert "杀" in toks
    assert "七杀" in toks


def test_query_side_includes_synonym_class_members():
    qtoks = set(encode_query("身轻"))
    assert "身弱" in qtoks or "失令" in qtoks


# ── splitter ───────────────────────────────────────────────────────────────


def test_split_known_chapter_yields_well_shaped_claims():
    raw = (CLASSICS / "ziping-zhenquan/35_lun-yin-shou.md").read_text(encoding="utf-8")
    claims = split_chapter("ziping-zhenquan", "ziping-zhenquan/35_lun-yin-shou.md", raw)
    assert claims
    assert all(c.id.startswith("ziping-zhenquan.") for c in claims)
    # NOTE: this chapter has principle+case mixed in every paragraph (the
    # author wrote it that way), so the splitter's coarse kind detector
    # marks everything 'case'. The LLM tagger fixes this via refined_kind.
    assert all(c.kind in {"principle", "case", "heuristic"} for c in claims)
    assert all(18 <= len(c.text) <= 260 for c in claims)


def test_split_pure_principle_paragraph_marked_principle():
    """A paragraph without ganzhi case strings should remain principle."""
    raw = ("# 论用神\n\n用神在月令，配以日干而生克变化，定其格局之高低；"
           "故格局成则贵，败则贱，岂可不细察焉。\n")
    claims = split_chapter("zpzq", "zpzq/test.md", raw)
    assert claims
    assert claims[0].kind == "principle"


def test_split_marks_extreme_judgement_paragraph():
    """A paragraph of absolutist 必/克/夭/凶 断语 with no 救应 should be
    flagged 'judgement' so policy can downweight it.

    Without this, 三命通会 卷十二's "必贫必夭" entries rank equally with
    子平真诠's structural rules and the LLM ends up echoing fatalistic
    断语 verbatim — exactly what GPT chap. 11 warns against."""
    raw = ("# 四言独步\n\n"
           "伤官见官，为祸百端，刑冲破害，主人凶夭，妻克子伤，必贫必贱。\n")
    claims = split_chapter("smt", "smt/juan-12.md", raw)
    assert claims
    assert claims[0].kind == "judgement", claims[0].kind


def test_split_judgement_with_remedy_stays_principle():
    """断语 paired with制化救应 in the same passage is still useful — keep
    as principle. Otherwise the splitter would torch every reasonable
    classical condition-and-remedy pairing."""
    raw = ("# 论七杀\n\n"
           "煞重身轻，主人贫夭刑伤；得印化煞、食制杀，则反成贵格。\n")
    claims = split_chapter("zpzq", "zpzq/test.md", raw)
    assert claims
    assert claims[0].kind == "principle", claims[0].kind


def test_split_marks_shensha_paragraph():
    """Pure shensha catalogue lines (桃花/驿马/孤辰/寡宿/...) are aux signal
    only — should be tagged 'shensha' so policy can downweight them."""
    raw = ("# 神煞\n\n"
           "桃花在子午卯酉，驿马居寅申巳亥，孤辰寡宿犯之婚迟，空亡逢之事多虚浮。\n")
    claims = split_chapter("smt", "smt/juan-02.md", raw)
    assert claims
    assert claims[0].kind == "shensha", claims[0].kind


def test_split_shensha_with_structural_logic_stays_principle():
    """If a passage names shensha but the bulk discusses 月令/格局/制化,
    keep it as principle so structural information isn't lost."""
    raw = ("# 论用神\n\n"
           "月令为命之提纲，用神所系，桃花虽动，配合得宜，亦无大碍，"
           "终以格局清纯、制化得当为要。\n")
    claims = split_chapter("zpzq", "zpzq/test.md", raw)
    assert claims
    assert claims[0].kind == "principle", claims[0].kind


def test_split_is_deterministic():
    raw = (CLASSICS / "ziping-zhenquan/35_lun-yin-shou.md").read_text(encoding="utf-8")
    a = split_chapter("ziping-zhenquan", "ziping-zhenquan/35_lun-yin-shou.md", raw)
    b = split_chapter("ziping-zhenquan", "ziping-zhenquan/35_lun-yin-shou.md", raw)
    assert [c.id for c in a] == [c.id for c in b]


def test_iter_classics_covers_all_books():
    seen = {rel.split("/", 1)[0] for rel, _ in iter_classics(CLASSICS)}
    assert seen == {
        "ditian-sui", "qiongtong-baojian", "sanming-tonghui",
        "yuanhai-ziping", "ziping-zhenquan",
    }


# ── BM25 ───────────────────────────────────────────────────────────────────


def _toy_claims() -> list[ClaimUnit]:
    return [
        ClaimUnit(id="a.1", book="x", chapter_file="x/a.md", chapter_title="A",
                  section=None, text="七杀重而身轻者宜用印化煞",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="a.2", book="x", chapter_file="x/a.md", chapter_title="A",
                  section=None, text="正官清纯而身旺乃富贵之造",
                  paragraph_idx=1, kind="principle"),
        ClaimUnit(id="a.3", book="x", chapter_file="x/a.md", chapter_title="A",
                  section=None, text="财格须身强方能任财",
                  paragraph_idx=2, kind="principle"),
    ]


def test_bm25_query_matches_target_claim():
    idx = build_bm25(_toy_claims())
    hits = idx.query("七杀身轻用印", k=3)
    assert hits[0][0] == "a.1"


def test_bm25_synonym_query():
    idx = build_bm25(_toy_claims())
    hits = idx.query("七煞身轻", k=3)
    assert hits and hits[0][0] == "a.1"


def test_bm25_pickle_round_trip(tmp_path):
    idx = build_bm25(_toy_claims())
    p = tmp_path / "bm25.pkl"
    save_bm25(idx, p)
    loaded = load_bm25(p)
    assert loaded is not None
    assert loaded.doc_ids == idx.doc_ids


# ── KG ─────────────────────────────────────────────────────────────────────


def test_kg_constraint_match():
    tags = [
        ClaimTags(claim_id="a", shishen=("七杀",), day_strength=("身弱",)),
        ClaimTags(claim_id="b", shishen=("正官",), day_strength=("身强",)),
        ClaimTags(claim_id="c", shishen=("七杀", "正印"), day_strength=("身弱",)),
    ]
    idx = build_kg(tags)
    matches = idx.match({"shishen": ("七杀",), "day_strength": ("身弱",)})
    assert set(matches) == {"a", "c"}
    assert all(s >= 1.0 for s in matches.values())


def test_kg_constraint_match_requires_all_fields():
    tags = [
        ClaimTags(claim_id="a", shishen=("七杀",), day_strength=("身弱",)),
        ClaimTags(claim_id="partial-shishen", shishen=("七杀",)),
        ClaimTags(claim_id="partial-strength", day_strength=("身弱",)),
    ]
    idx = build_kg(tags)
    matches = idx.match({"shishen": ("七杀",), "day_strength": ("身弱",)})
    assert set(matches) == {"a"}


def test_kg_synonym_term():
    tags = [ClaimTags(claim_id="a", shishen=("七杀",))]
    idx = build_kg(tags)
    assert "a" in idx.match({"shishen": ("煞",)})


# ── intents ────────────────────────────────────────────────────────────────


def _chart_jia_qisha() -> dict:
    return {
        "rizhu": "甲木", "geju": "七杀格", "dayStrength": "身弱",
        "sizhu": {"year": "壬寅", "month": "丁卯", "day": "甲申", "hour": "庚午"},
        "geJu": {"mainCandidate": {"shishen": "七杀"}},
        "yongshenDetail": {
            "candidates": [
                {"method": "扶抑", "name": "印", "source": "滴天髓·衰旺"},
            ],
        },
    }


def _chart_jia_shen_qisha() -> dict:
    return {
        "rizhu": "甲木", "geju": "七杀格", "dayStrength": "身弱",
        "sizhu": {"year": "癸未", "month": "庚申", "day": "甲戌", "hour": "戊辰"},
        "geJu": {
            "mainCandidate": {"name": "七杀格", "shishen": "七杀"},
            "decisionNote": "四孟月 申，庚 透干（本气优先），取七杀格",
        },
        "yongshen": "丁火",
        "yongshenDetail": {
            "primary": "丁火",
            "candidates": [
                {"method": "扶抑", "name": "丁火", "source": "用神"},
            ],
        },
    }


def test_intents_chitchat_returns_empty():
    assert bazi_chart_to_intents(_chart_jia_qisha(), "chitchat") == []


def test_intents_meta_emits_full_axis_set():
    intents = bazi_chart_to_intents(_chart_jia_qisha(), "meta", "杀重身轻怎么办")
    kinds = [i.kind for i in intents]
    assert "tiaohou" in kinds
    assert "main_geju" in kinds
    assert any(k.startswith("yongshen.") for k in kinds)
    assert "domain.meta" in kinds
    assert "combo.shaqing_yinzhong" in kinds  # 七杀 + 身弱
    assert "user_msg" in kinds


def test_intents_main_geju_carries_constraints():
    intents = bazi_chart_to_intents(_chart_jia_qisha(), "meta")
    main = next(i for i in intents if i.kind == "main_geju")
    assert main.constraints["shishen"] == ("七杀",)
    assert main.constraints["day_strength"] == ("身弱",)


def test_intents_liunian_keeps_timing_domain():
    intents = bazi_chart_to_intents(_chart_jia_qisha(), "liunian")
    assert "tiaohou" in [i.kind for i in intents]
    domain = next(i for i in intents if i.kind == "domain.liunian")
    assert domain.constraints["domain"] == ("行运",)


def test_intents_day_hour_anchor_includes_full_day_pillar():
    intents = bazi_chart_to_intents(_chart_jia_shen_qisha(), "wealth", "我的财运怎么样")
    day_hour = next(i for i in intents if i.kind == "combo.day_hour")
    assert "甲戌日戊辰時" in day_hour.text
    assert "甲日戊辰時" in day_hour.text
    assert "偏财" in day_hour.text


# ── tagger parser ──────────────────────────────────────────────────────────


def test_tagger_response_parser_with_fence_and_extras():
    text = """```json
{"shishen":["七杀"],"yongshen_method":["扶抑","made-up"],
 "authority":0.8,"confidence":0.7,"future":"ok"}
```"""
    parsed = parse_response(text, "x.1")
    assert parsed["shishen"] == ("七杀",)
    assert parsed["yongshen_method"] == ("扶抑",)  # "made-up" filtered out
    assert parsed["authority"] == 0.8
    assert parsed["tagger_confidence"] == 0.7


def test_tagger_response_parser_garbage():
    assert parse_response("not json", "x") == {}
    assert parse_response("[1,2,3]", "x") == {}


def test_vocab_no_duplicates():
    for k, v in VOCAB.items():
        assert len(v) == len(set(v)), f"duplicate in VOCAB[{k}]"


# ── selector parser ────────────────────────────────────────────────────────


def test_selector_picks_parser():
    text = '{"picks":[{"id":"a.1","reason":"直接对题"},{"id":"a.2","reason":""}]}'
    picks = parse_picks(text, valid_ids={"a.1", "a.2", "a.3"})
    assert picks == [("a.1", "直接对题", ""), ("a.2", "", "")]


def test_selector_picks_drops_invalid_ids():
    text = '{"picks":[{"id":"unknown","reason":"x"},{"id":"a.1","reason":"y"}]}'
    picks = parse_picks(text, valid_ids={"a.1"})
    assert picks == [("a.1", "y", "")]


def test_selector_picks_handles_garbage():
    assert parse_picks("not json", valid_ids={"a"}) == []
    assert parse_picks('{"foo": "bar"}', valid_ids={"a"}) == []


def test_selector_picks_parses_supports_field():
    """Selector v2: picks may carry a ``supports`` field naming which
    sub-claim the citation answers (e.g. 'tiaohou' / 'main_geju' /
    'pattern' / 'climate'). Empty / missing => "" so callers can group."""
    text = (
        '{"picks":[{"id":"a.1","reason":"调候段","supports":"tiaohou"},'
        '{"id":"a.2","reason":"格局段","supports":"main_geju"},'
        '{"id":"a.3","reason":"无标注"}]}'
    )
    picks = parse_picks(text, valid_ids={"a.1", "a.2", "a.3"})
    assert picks == [
        ("a.1", "调候段", "tiaohou"),
        ("a.2", "格局段", "main_geju"),
        ("a.3", "无标注", ""),
    ]


def test_selector_select_propagates_supports_to_hit(monkeypatch):
    """When selector returns ``supports``, RetrievalHit.claim_supported
    surfaces it for downstream prompt rendering."""
    candidate = Candidate(
        claim=ClaimUnit(
            id="qt.1", book="qiongtong-baojian",
            chapter_file="qiongtong-baojian/02_lun-jia-mu.md",
            chapter_title="论甲木", section="正月",
            text="正月甲木初春余寒,先丙后癸。",
            paragraph_idx=0, kind="principle",
        ),
        tags=ClaimTags(claim_id="qt.1"),
        fused_score=0.9,
    )

    async def fake_call(messages, *, timeout):
        return '{"picks":[{"id":"qt.1","reason":"日干月令对应","supports":"climate"}]}'

    monkeypatch.setattr("app.retrieval2.selector._call_deepseek", fake_call)
    hits = asyncio.run(selector_select({}, [], "甲木冬天怎么调候", [candidate], k=1))
    assert hits[0].claim_supported == "climate"


def test_selector_llm_call_disables_thinking_for_json(monkeypatch):
    from app.retrieval2 import selector as selector_module

    captured = {}

    async def fake_chat_once_with_fallback(**kwargs):
        captured.update(kwargs)
        return '{"picks":[]}', "fake-model"

    monkeypatch.setattr("app.llm.client.chat_once_with_fallback", fake_chat_once_with_fallback)
    text = asyncio.run(selector_module._call_deepseek([], timeout=1.0))

    assert text == '{"picks":[]}'
    assert captured["tier"] == "fast"
    assert captured["disable_thinking"] is True


def test_selector_successful_partial_pick_is_not_padded(monkeypatch):
    candidates = [
        Candidate(
            claim=ClaimUnit(
                id="good", book="ditian-sui",
                chapter_file="ditian-sui/liu-qin-lun_01_fu-qi.md",
                chapter_title="夫妻", section=None,
                text="夫财以妻论，夫妻之法须看喜忌。",
                paragraph_idx=0, kind="principle",
            ),
            tags=ClaimTags(claim_id="good", domain=("六亲",)),
            fused_score=0.9,
        ),
        Candidate(
            claim=ClaimUnit(
                id="padding", book="qiongtong-baojian",
                chapter_file="qiongtong-baojian/02_lun-jia-mu.md",
                chapter_title="论甲木", section="三春甲木",
                text="甲木调候取用，与婚姻问题不直接相关。",
                paragraph_idx=0, kind="principle",
            ),
            tags=ClaimTags(claim_id="padding", domain=("调候",)),
            fused_score=0.8,
        ),
    ]

    async def fake_call(messages, *, timeout):
        return '{"picks":[{"id":"good","reason":"直接谈夫妻"}]}'

    monkeypatch.setattr("app.retrieval2.selector._call_deepseek", fake_call)
    hits = asyncio.run(selector_select({}, [], "婚姻正缘怎么看", candidates, k=3))
    assert [h.claim.id for h in hits] == ["good"]


# ── policy chunk_type weighting ────────────────────────────────────────────


def test_policy_judgement_claim_is_downweighted_vs_principle():
    """A judgement claim ('必贫必夭克妻') and a principle claim with the
    same domain tag should not score equally. Judgement is downweighted so
    the principle (e.g. 子平真诠 论用神成败) outranks 三命通会 卷十二
    fatalistic chants."""
    from app.retrieval2.policy import RetrievalPolicy

    policy = RetrievalPolicy(
        kind="verdict",
        positive_domains=("格局成败",),
    )
    common = dict(book="x", chapter_title="t", section=None, paragraph_idx=0)
    judgement = ClaimUnit(
        id="j", chapter_file="smt/juan-12.md",
        text="伤官见官，必贫必贱，妻克子伤。",
        kind="judgement", **common,
    )
    principle = ClaimUnit(
        id="p", chapter_file="zpzq/09.md",
        text="用神在月令，配以日干而生克变化，定其格局之高低。",
        kind="principle", **common,
    )
    tags = ClaimTags(claim_id="any", domain=("格局成败",))
    j_score = policy.boost(judgement, tags)
    p_score = policy.boost(principle, tags)
    assert j_score < p_score, f"judgement {j_score} should rank below principle {p_score}"


def test_policy_shensha_claim_is_downweighted_vs_principle():
    """A shensha-only paragraph (神煞名罗列) ranks below structural论述."""
    from app.retrieval2.policy import RetrievalPolicy

    policy = RetrievalPolicy(kind="meta")
    common = dict(book="x", chapter_title="t", section=None, paragraph_idx=0)
    shensha = ClaimUnit(
        id="s", chapter_file="smt/juan-02.md",
        text="桃花在子午卯酉，驿马在寅申巳亥。",
        kind="shensha", **common,
    )
    principle = ClaimUnit(
        id="p", chapter_file="zpzq/09.md",
        text="用神成败，须究月令深浅。",
        kind="principle", **common,
    )
    tags = ClaimTags(claim_id="any")
    assert policy.boost(shensha, tags) < policy.boost(principle, tags)


def test_policy_uses_refined_kind_when_set():
    """If tagger refined an originally-principle claim into judgement
    (because LLM saw absolutist words splitter heuristic missed),
    the refined value wins."""
    from app.retrieval2.policy import RetrievalPolicy

    policy = RetrievalPolicy(kind="meta")
    common = dict(book="x", chapter_title="t", section=None, paragraph_idx=0)
    looks_like_principle = ClaimUnit(
        id="x", chapter_file="smt/x.md",
        text="此处含细腻语义，splitter 没识别，但 LLM 标了 judgement。",
        kind="principle", **common,
    )
    refined_to_judgement = ClaimTags(
        claim_id="x", domain=(), refined_kind="judgement",
    )
    refined_to_principle = ClaimTags(
        claim_id="x", domain=(), refined_kind="principle",
    )
    s_low = policy.boost(looks_like_principle, refined_to_judgement)
    s_high = policy.boost(looks_like_principle, refined_to_principle)
    assert s_low < s_high


def test_selector_llm_failure_still_falls_back_to_fused(monkeypatch):
    candidates = [
        Candidate(
            claim=ClaimUnit(
                id="a", book="ditian-sui",
                chapter_file="ditian-sui/liu-qin-lun_28_sui-yun.md",
                chapter_title="岁运", section=None,
                text="太岁管一年否泰。",
                paragraph_idx=0, kind="principle",
            ),
            tags=ClaimTags(claim_id="a", domain=("行运",)),
            fused_score=0.9,
        ),
        Candidate(
            claim=ClaimUnit(
                id="b", book="ziping-zhenquan",
                chapter_file="ziping-zhenquan/25_lun-xing-yun.md",
                chapter_title="论行运", section=None,
                text="论运与看命无二法。",
                paragraph_idx=0, kind="principle",
            ),
            tags=ClaimTags(claim_id="b", domain=("行运",)),
            fused_score=0.8,
        ),
    ]

    async def fake_call(messages, *, timeout):
        raise TimeoutError("boom")

    monkeypatch.setattr("app.retrieval2.selector._call_deepseek", fake_call)
    hits = asyncio.run(selector_select({}, [], "流年", candidates, k=2))
    assert [h.claim.id for h in hits] == ["a", "b"]


# ── service round-trip with stub selector ─────────────────────────────────


def _build_mini_index(root: Path) -> None:
    p = storage.paths(root)
    claims = [
        ClaimUnit(id="zpzq.35.0007", book="ziping-zhenquan",
                  chapter_file="ziping-zhenquan/35_lun-yin-shou.md",
                  chapter_title="论印绶", section=None,
                  text="有用偏官者，偏官本非美物，藉其生印，不得已而用之。"
                       "故必身重印轻，或身轻印重，有所不足，始为有性。",
                  paragraph_idx=4, kind="principle"),
        ClaimUnit(id="dts.tg.1", book="ditian-sui",
                  chapter_file="ditian-sui/tong-shen-lun_20_tong-guan.md",
                  chapter_title="通关", section=None,
                  text="官煞两停身轻者，喜印通关化煞使日主得用。",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="qt.甲.卯月", book="qiongtong-baojian",
                  chapter_file="qiongtong-baojian/02_lun-jia-mu.md",
                  chapter_title="论甲木", section="卯月",
                  text="甲木生于卯月，气候渐和，用丁火洩秀以庚金为佐。",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="qt.甲.申月", book="qiongtong-baojian",
                  chapter_file="qiongtong-baojian/02_lun-jia-mu.md",
                  chapter_title="论甲木", section="三秋甲木",
                  text="七月甲木，丁火为尊，庚金次之，庚金不可少。",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="smt.甲申月", book="sanming-tonghui",
                  chapter_file="sanming-tonghui/juan-04.md",
                  chapter_title="三命通会 · 卷四", section="申月",
                  text="甲日申月为偏官，喜身旺合制，忌身弱正官运，尤忌再见七杀。",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="smt.甲申时", book="sanming-tonghui",
                  chapter_file="sanming-tonghui/juan-08.md",
                  chapter_title="三命通会 · 卷八", section="六甲日申时断",
                  text="甲日壬申时，甲木绝在申，明枭暗鬼，须丙戊制化。",
                  paragraph_idx=0, kind="heuristic"),
        ClaimUnit(id="smt.甲戌戊辰.0", book="sanming-tonghui",
                  chapter_file="sanming-tonghui/juan-08.md",
                  chapter_title="三命通会 · 卷八", section="六甲日戊辰時斷",
                  text="甲日戊辰时天财坐库，时上偏财遇龙守库，"
                       "主为商贾发财，田园广盛。",
                  paragraph_idx=8, kind="heuristic"),
        ClaimUnit(id="smt.甲戌戊辰.1", book="sanming-tonghui",
                  chapter_file="sanming-tonghui/juan-08.md",
                  chapter_title="三命通会 · 卷八", section="六甲日戊辰時斷",
                  text="甲戌日戊辰时大富，年月扶合亦贵；"
                       "时上偏财不用多，运通财旺官生至。",
                  paragraph_idx=8, kind="principle"),
        ClaimUnit(id="zpzq.偏官", book="ziping-zhenquan",
                  chapter_file="ziping-zhenquan/39_lun-pian-guan.md",
                  chapter_title="论偏官", section=None,
                  text="煞以攻身，控制得宜，煞为我用；煞重身轻，用食则身不能当，不若转而就印。",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="dts.fuqi.1", book="ditian-sui",
                  chapter_file="ditian-sui/liu-qin-lun_01_fu-qi.md",
                  chapter_title="夫妻", section=None,
                  text="夫财以妻论，财神清者不争不妒，四柱配合须分日主衰旺喜忌。",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="dts.zinv.1", book="ditian-sui",
                  chapter_file="ditian-sui/liu-qin-lun_02_zi-nv.md",
                  chapter_title="子女", section=None,
                  text="杀重身轻，只要印比，喜神看与杀相连，子女之论不可执一。",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="dts.hezhizhang.rich", book="ditian-sui",
                  chapter_file="ditian-sui/liu-qin-lun_05_he-zhi-zhang.md",
                  chapter_title="何知章", section=None,
                  text="何知其人富，财气通门户。身旺财弱无官者，必要有食伤。",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="yh.正财", book="yuanhai-ziping",
                  chapter_file="yuanhai-ziping/06_shi-shen_zheng-cai-pian-cai.md",
                  chapter_title="十神：正财、偏财", section="论正财",
                  text="正财乃我克之财，喜身旺财旺，忌比劫夺财。",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="yh.偏财", book="yuanhai-ziping",
                  chapter_file="yuanhai-ziping/06_shi-shen_zheng-cai-pian-cai.md",
                  chapter_title="十神：正财、偏财", section="论偏财",
                  text="何谓之偏财，乃众人之财，只恐兄弟姊妹有夺之。",
                  paragraph_idx=1, kind="principle"),
        ClaimUnit(id="zpzq.财", book="ziping-zhenquan",
                  chapter_file="ziping-zhenquan/33_lun-cai.md",
                  chapter_title="论财", section=None,
                  text="财为我克，使用之物也，以能生官，所以为美。",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="zpzq.财取运", book="ziping-zhenquan",
                  chapter_file="ziping-zhenquan/34_lun-cai-qu-yun.md",
                  chapter_title="论财取运", section=None,
                  text="财格取运，财旺生官者，运喜身旺印绶。",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="smt.generic.money", book="sanming-tonghui",
                  chapter_file="sanming-tonghui/juan-12.md",
                  chapter_title="三命通会 · 卷十二", section="四言独步",
                  text="喜茂财源，冬天水木泛，名利总虚浮，财官气候须详。",
                  paragraph_idx=0, kind="heuristic"),
        ClaimUnit(id="zpzq.xingyun", book="ziping-zhenquan",
                  chapter_file="ziping-zhenquan/25_lun-xing-yun.md",
                  chapter_title="论行运", section=None,
                  text="论运与看命无二法，岁运干支须配原局喜忌，成格变格各有所宜。",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="dts.ganzhi.generic", book="ditian-sui",
                  chapter_file="ditian-sui/tong-shen-lun_09_gan-zhi-zong-lun.md",
                  chapter_title="干支总论", section=None,
                  text="甲申日坐杀印，亦须论岁运太岁，但此为干支泛论不可替代行运专章。",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="qt.壬.子月", book="qiongtong-baojian",
                  chapter_file="qiongtong-baojian/10_lun-ren-shui.md",
                  chapter_title="论壬水", section="三冬壬水",
                  text="十一月壬水，阳刃帮身，较前更旺，先取戊土，次用丙火。",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="qt.丙.子月", book="qiongtong-baojian",
                  chapter_file="qiongtong-baojian/04_lun-bing-huo.md",
                  chapter_title="论丙火", section="三冬丙火",
                  text="十一月丙火，冬至一阳生，弱中复强，壬水为最，戊土佐之。",
                  paragraph_idx=0, kind="principle"),
        # 女命章 (滴天髓 06) — for relationship female test
        ClaimUnit(id="dts.nv-ming.1", book="ditian-sui",
                  chapter_file="ditian-sui/liu-qin-lun_06_nv-ming-zhang.md",
                  chapter_title="女命章", section=None,
                  text="女命须看夫子两宫，官星为夫，食伤为子；清纯则贵，混杂为浊。",
                  paragraph_idx=0, kind="principle"),
        # 健康相关:衰旺 / 寒暖 / 疾病性情 / 调候致病 — for health expansion test
        ClaimUnit(id="dts.shuai-wang.1", book="ditian-sui",
                  chapter_file="ditian-sui/tong-shen-lun_17_shuai-wang.md",
                  chapter_title="衰旺", section=None,
                  text="衰旺无差为中和，偏枯太过则生灾。日主衰极宜从其势，旺极忌克泄过重。",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="dts.han-nuan.1", book="ditian-sui",
                  chapter_file="ditian-sui/tong-shen-lun_29_han-nuan.md",
                  chapter_title="寒暖", section=None,
                  text="寒甚则冰，暖盛则燥；金水寒湿宜火土温之，木火燥烈喜水以润之。",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="yh.ji-bing.1", book="yuanhai-ziping",
                  chapter_file="yuanhai-ziping/03_lun-ji-bing-xing-qing.md",
                  chapter_title="论疾病性情", section=None,
                  text="火土燥烈者多燥热血热病；水寒木滞者多风寒湿郁；金弱火多多咳嗽。",
                  paragraph_idx=0, kind="principle"),
        # 正官章 — for meta zheng-guan generalization test
        ClaimUnit(id="zpzq.zheng-guan", book="ziping-zhenquan",
                  chapter_file="ziping-zhenquan/31_lun-zheng-guan.md",
                  chapter_title="论正官", section=None,
                  text="正官者，我克我者也，主贵气；喜身旺、官清、财印相辅，忌伤官、刑冲、官杀混杂。",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="zpzq.zheng-guan.qu-yun", book="ziping-zhenquan",
                  chapter_file="ziping-zhenquan/32_lun-zheng-guan-qu-yun.md",
                  chapter_title="论正官取运", section=None,
                  text="正官取运，运喜财印；忌伤官、七杀混杂之地。",
                  paragraph_idx=0, kind="principle"),
        # persona 多样性: 滴天髓性情 + 子平真诠 04 + 渊海04干支体象 + 三命通会论丁日
        ClaimUnit(id="dts.xing-qing.0", book="ditian-sui",
                  chapter_file="ditian-sui/liu-qin-lun_24_xing-qing.md",
                  chapter_title="性情", section=None,
                  text="五气不戾，性情中和；浊乱偏枯，性情乖逆。",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="dts.xing-qing.1", book="ditian-sui",
                  chapter_file="ditian-sui/liu-qin-lun_24_xing-qing.md",
                  chapter_title="性情", section=None,
                  text="火烈而性燥者，遇金水之节；水奔而性柔者，全金木之神。",
                  paragraph_idx=1, kind="principle"),
        ClaimUnit(id="zpzq.04.peihe", book="ziping-zhenquan",
                  chapter_file="ziping-zhenquan/04_lun-shi-gan-pei-he-xing-qing.md",
                  chapter_title="论十干配合性情", section=None,
                  text="合化之义，以十干阴阳相配而成,各有性情之偏正。",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="yh.04.gan-zhi-ti-xiang", book="yuanhai-ziping",
                  chapter_file="yuanhai-ziping/04_gan-zhi-ti-xiang.md",
                  chapter_title="干支体象", section="天干体象",
                  text="丁火如灯烛炉冶之火，性温而柔中带刚。",
                  paragraph_idx=0, kind="principle"),
        ClaimUnit(id="smt.juan-04.lun-ding", book="sanming-tonghui",
                  chapter_file="sanming-tonghui/juan-04.md",
                  chapter_title="三命通会·卷四", section="论丁日生人",
                  text="丁日生人，性情温和，外柔内刚，遇甲木而文采，逢庚金而劳碌。",
                  paragraph_idx=0, kind="principle"),
    ]
    tags = [
        ClaimTags(claim_id="zpzq.35.0007", shishen=("七杀", "正印"),
                  day_strength=("身轻",), yongshen_method=("扶抑",), authority=0.95),
        ClaimTags(claim_id="dts.tg.1", shishen=("七杀", "正印"),
                  day_strength=("身轻",), yongshen_method=("通关",), authority=0.9),
        ClaimTags(claim_id="qt.甲.卯月", day_gan=("甲",), month_zhi=("卯",),
                  yongshen_method=("调候",), authority=0.85),
        ClaimTags(claim_id="qt.甲.申月", domain=("调候", "用神取舍", "格局成败"),
                  shishen=("七杀", "伤官"), yongshen_method=("调候", "扶抑"),
                  season=("秋",), day_gan=("甲",), month_zhi=("申",),
                  geju=("七杀格",), authority=0.9),
        ClaimTags(claim_id="smt.甲申月", domain=("格局成败", "用神取舍", "财官"),
                  shishen=("七杀",), yongshen_method=("扶抑", "格局"),
                  day_strength=("身弱",), season=("秋",), day_gan=("甲",),
                  month_zhi=("申",), authority=0.85),
        ClaimTags(claim_id="smt.甲申时", domain=("格局成败",), shishen=("七杀", "偏印"),
                  day_gan=("甲",), month_zhi=("申",), authority=0.7),
        ClaimTags(claim_id="smt.甲戌戊辰.0", domain=("财官",), shishen=("偏财",),
                  day_gan=("甲",), month_zhi=("申",), authority=0.75),
        ClaimTags(claim_id="smt.甲戌戊辰.1", domain=("财官",), shishen=("偏财",),
                  day_gan=("甲",), month_zhi=("申",), authority=0.75),
        ClaimTags(claim_id="zpzq.偏官", domain=("格局成败",), shishen=("七杀",),
                  day_strength=("身弱",), geju=("七杀格",), authority=0.95),
        ClaimTags(claim_id="dts.fuqi.1", domain=("六亲",), shishen=("正财",),
                  authority=0.95),
        ClaimTags(claim_id="dts.zinv.1", domain=("六亲",), shishen=("七杀", "正印"),
                  day_strength=("身轻",), authority=0.9),
        ClaimTags(claim_id="dts.hezhizhang.rich", domain=("财官",),
                  shishen=("正财", "食神"), day_strength=("身旺",), authority=0.95),
        ClaimTags(claim_id="yh.正财", domain=("财官",), shishen=("正财",),
                  day_strength=("身旺",), authority=0.9),
        ClaimTags(claim_id="yh.偏财", domain=("财官",), shishen=("偏财",),
                  authority=0.88),
        ClaimTags(claim_id="zpzq.财", domain=("财官",), shishen=("正财", "偏财"),
                  authority=0.92),
        ClaimTags(claim_id="zpzq.财取运", domain=("财官",), shishen=("正财", "偏财"),
                  authority=0.9),
        ClaimTags(claim_id="smt.generic.money", domain=("财官", "调候"),
                  shishen=("正财", "正官"), authority=0.5),
        ClaimTags(claim_id="zpzq.xingyun", domain=("行运",), authority=0.95),
        ClaimTags(claim_id="dts.ganzhi.generic", domain=("行运",), shishen=("七杀",),
                  authority=0.9),
        ClaimTags(claim_id="qt.壬.子月", domain=("调候", "用神取舍"),
                  day_gan=("壬",), month_zhi=("子",), season=("冬",),
                  yongshen_method=("调候",), authority=0.95),
        ClaimTags(claim_id="qt.丙.子月", domain=("调候",),
                  day_gan=("丙",), month_zhi=("子",), season=("冬",),
                  yongshen_method=("调候",), authority=0.85),
        # 女命章 tag
        ClaimTags(claim_id="dts.nv-ming.1", domain=("六亲", "女命"),
                  shishen=("正官", "食神", "伤官"), authority=0.95),
        # health 扩展 tags
        ClaimTags(claim_id="dts.shuai-wang.1", domain=("用神取舍",),
                  day_strength=("身弱", "身强", "中和"), authority=0.9),
        ClaimTags(claim_id="dts.han-nuan.1", domain=("调候",),
                  yongshen_method=("调候",), authority=0.9),
        ClaimTags(claim_id="yh.ji-bing.1", domain=("疾病", "性情"),
                  authority=0.9),
        # 正官章 tags
        ClaimTags(claim_id="zpzq.zheng-guan", domain=("格局成败",),
                  shishen=("正官",), geju=("正官格",), authority=0.95),
        ClaimTags(claim_id="zpzq.zheng-guan.qu-yun", domain=("格局成败", "行运"),
                  shishen=("正官",), geju=("正官格",), authority=0.9),
        # persona 多样性 tags
        ClaimTags(claim_id="dts.xing-qing.0", domain=("性情",), authority=0.95),
        ClaimTags(claim_id="dts.xing-qing.1", domain=("性情",), authority=0.93),
        ClaimTags(claim_id="zpzq.04.peihe", domain=("性情",),
                  shishen=("比肩", "劫财"), authority=0.92),
        ClaimTags(claim_id="yh.04.gan-zhi-ti-xiang", domain=("外貌", "性情"),
                  day_gan=("丁",), authority=0.92),
        ClaimTags(claim_id="smt.juan-04.lun-ding", domain=("性情",),
                  day_gan=("丁",), authority=0.9),
    ]
    storage.write_claims(p.claims, claims)
    storage.write_tags(p.tags, tags)
    save_bm25(build_bm25(claims), p.bm25)
    storage.write_manifest(p.manifest, classics_root=Path("/no/such"),
                           file_hashes={}, stats={})


@pytest.fixture
def mini_index(tmp_path, monkeypatch):
    """Builds a tiny on-disk index and patches the selector to a no-LLM stub
    so service tests don't need an API key.

    Stub returns top-K by fused_score (== fallback path)."""
    root = tmp_path / "idx"
    root.mkdir()
    _build_mini_index(root)

    async def stub_select(chart, intents, user_msg, candidates, *, k=6,
                          max_candidates=30, timeout_seconds=20.0, policy_hint=""):
        from app.retrieval2.types import RetrievalHit
        return [
            RetrievalHit(claim=c.claim, tags=c.tags,
                         score=c.fused_score, reason="stub")
            for c in list(candidates)[:k]
        ]

    monkeypatch.setattr("app.retrieval2.selector.select", stub_select)
    service.reset_cache()
    return root


def test_service_returns_v1_shape(mini_index):
    chart = _chart_jia_qisha()
    hits = asyncio.run(service.retrieve_for_chart(
        chart, kind="meta", user_message="杀重身轻怎么办",
        index_root=mini_index,
    ))
    assert hits
    h0 = hits[0]
    assert {"source", "file", "scope", "chars", "text"} <= h0.keys()
    assert h0["chars"] == len(h0["text"])
    assert not h0["scope"].startswith("claim:")


def test_service_returns_display_scope_not_internal_claim_id(mini_index):
    hits = asyncio.run(service.retrieve_for_chart(
        _chart_jia_qisha(), kind="meta", index_root=mini_index,
        use_selector=False,
    ))
    by_file = {h["file"]: h for h in hits}
    assert by_file["qiongtong-baojian/02_lun-jia-mu.md"]["scope"] == "卯月"


def test_service_chitchat_returns_empty(mini_index):
    hits = asyncio.run(service.retrieve_for_chart(
        _chart_jia_qisha(), kind="chitchat", index_root=mini_index,
    ))
    assert hits == []


def test_service_use_selector_false_returns_top_fused(mini_index):
    """use_selector=False is the deterministic fallback path."""
    hits = asyncio.run(service.retrieve_for_chart(
        _chart_jia_qisha(), kind="meta", index_root=mini_index,
        use_selector=False,
    ))
    assert hits


def test_relationship_prefers_spouse_not_children(mini_index):
    hits = asyncio.run(service.retrieve_for_chart(
        _chart_jia_qisha(), kind="relationship", user_message="我的婚姻正缘怎么看",
        index_root=mini_index, use_selector=False, final_k=4,
    ))
    assert hits[0]["file"] == "ditian-sui/liu-qin-lun_01_fu-qi.md"
    assert all("zi-nv" not in h["file"] for h in hits[:3])


def test_relationship_male_chart_pulls_in_cai_chapters(mini_index):
    """男命:财=妻,关系问题除了夫妻章还应该见到论财章/何知章。
    传统命理里男命的"妻论"散在 子平真诠 论财 / 滴天髓 何知章 / 渊海正偏财,
    女命 only 的关系 policy 把这些堵住,男命问关系反而看不到自己的"妻"信号。"""
    chart = dict(_chart_jia_qisha())
    chart["gender"] = "male"
    hits = asyncio.run(service.retrieve_for_chart(
        chart, kind="relationship", user_message="我的妻缘和婚姻怎么看",
        index_root=mini_index, use_selector=False, final_k=8,
    ))
    files = {h["file"] for h in hits}
    # 男命应该能召回到财章 (论财 / 何知章 / 渊海正偏财)
    has_cai_source = any(
        "lun-cai" in f or "he-zhi-zhang" in f or "zheng-cai-pian-cai" in f
        for f in files
    )
    assert has_cai_source, f"男命婚姻问题应召回财章,实际 files: {files}"


def test_relationship_female_chart_includes_nv_ming_zhang(mini_index):
    """女命:滴天髓·女命章 是核心,但当前 policy allowed 只挂了
    fu-qi 章和 yuanhai 11 — 滴天髓 06_nv-ming-zhang 反而被 reject
    到了。这是个 policy bug,女命问关系应该首选 nv-ming-zhang。"""
    chart = dict(_chart_jia_qisha())
    chart["gender"] = "female"
    hits = asyncio.run(service.retrieve_for_chart(
        chart, kind="relationship", user_message="我的婚姻夫缘怎么看",
        index_root=mini_index, use_selector=False, final_k=6,
    ))
    files = [h["file"] for h in hits]
    has_nv_ming_zhang = any("nv-ming-zhang" in f or "nv-ming-lun" in f for f in files)
    assert has_nv_ming_zhang, f"女命婚姻应召回女命章,实际 files: {files}"


def test_health_pulls_more_than_one_source(mini_index):
    """健康问题不应该只走 ditian ji-bing 一份。命理上"病=偏枯",
    应该同时见到衰旺 / 寒暖 / 调候层依据(穷通日干月令)。"""
    chart = _chart_jia_qisha()
    hits = asyncio.run(service.retrieve_for_chart(
        chart, kind="section:health", user_message="我容易得什么病",
        index_root=mini_index, use_selector=False, final_k=6,
    ))
    files = {h["file"] for h in hits}
    # 至少应该有两个不同来源 (ji-bing 和 衰旺/寒暖/调候 任一)
    has_ji_bing = any("ji-bing" in f for f in files)
    has_struct_aux = any(
        "shuai-wang" in f or "han-nuan" in f or "zao-shi" in f
        or "qiongtong-baojian" in f or "ji-bing-xing-qing" in f
        for f in files
    )
    assert has_ji_bing and has_struct_aux, (
        f"健康检索应同时含 ji-bing 章和结构层依据 (衰旺/寒暖/调候),"
        f"实际 files: {files}"
    )


def test_intents_emit_po_ge_for_main_geju():
    """主十神泛化的反向: 应该发一条'破格条款'intent, 用来检索
    '正官格忌伤官刑冲'这类反向论述。命理上看一个格局的成败必须看
    破格因素,只查正向就漏一半。"""
    chart = _chart_jia_qisha()  # 七杀格
    intents = bazi_chart_to_intents(chart, "meta")
    po_ge = [i for i in intents if i.kind == "combo.po_ge"]
    assert po_ge, "七杀格 chart 应发出 combo.po_ge intent"
    text = po_ge[0].text
    # 七杀格的破格条款应含 "杀重身轻" 或 "无制" 这类反向词
    assert any(t in text for t in ("杀重", "无制", "破"))


def test_intents_emit_day_branch_relation_when_chong():
    """日支被冲是关系/性格分析的关键信号 —— 应该发专门 intent。"""
    chart = {
        "rizhu": "甲木", "geju": "建禄格", "dayStrength": "中和",
        # 日支寅,时支申 → 寅申冲, 日支被冲
        "sizhu": {"year": "壬子", "month": "癸卯", "day": "甲寅", "hour": "壬申"},
        "geJu": {"mainCandidate": {"shishen": "比肩"}},
        "yongshenDetail": {"candidates": []},
        "zhiRelations": {
            "chong": [{"a": "寅", "b": "申", "idx_a": 2, "idx_b": 3}],
            "liuHe": [], "sanHe": [], "banHe": [], "sanHui": [],
        },
    }
    # service.py strips "section:" before calling intents — call directly with stripped kind
    intents = bazi_chart_to_intents(chart, "relationship", "婚姻怎么样")
    day_branch = [i for i in intents if i.kind == "combo.day_branch_relation"]
    assert day_branch, "日支被冲应发 combo.day_branch_relation intent"
    assert "日支" in day_branch[0].text or "日宫" in day_branch[0].text


def test_intents_emit_school_compare_when_yongshen_warning_present():
    """当 yongshenDetail.warnings 含两派分歧时,应同时发调候派和格局派
    两个并行 intent,让 selector 能各取一段做对照。"""
    chart = {
        "rizhu": "甲木", "geju": "正官格", "dayStrength": "中和",
        "sizhu": {"year": "壬寅", "month": "丁未", "day": "甲申", "hour": "庚午"},
        "geJu": {"mainCandidate": {"shishen": "正官"}},
        "yongshenDetail": {
            "primary": "丁火",
            "primaryReason": "以调候为主",
            "candidates": [
                {"method": "调候", "name": "丁火", "source": "穷通宝鉴"},
                {"method": "格局", "name": "庚金", "source": "子平真诠"},
            ],
            "warnings": ["调候用神与格局用神不同 —— 古籍两派各有取法"],
        },
    }
    intents = bazi_chart_to_intents(chart, "meta", "我这盘整体看")
    kinds = [i.kind for i in intents]
    # 应该同时有 school.tiaohou 和 school.geju 两个并行 intent
    assert "school.tiaohou" in kinds, f"应发调候派 intent, 实际 kinds: {kinds}"
    assert "school.geju" in kinds, f"应发格局派 intent, 实际 kinds: {kinds}"


def test_compound_retrieval_unions_multiple_policies(mini_index):
    """Compound retrieval (driven by router's primary + secondary intents):
    跨轴问题应该让多个 policy 各自的核心章节都进 final hits。
    例:meta + personality 应该同时见到 主十神/格局 类材料 和 性情/画像 类材料。

    比对单 policy 检索:
      * 单 personality: 只能拿到性情章 / 干支体象,完全没格局轴
      * 单 meta: 只能拿到格局章 / 调候,完全没性情画像
      * compound: 两轴混合,这是给"讲整体"问题的正确答案。"""
    chart = {
        "rizhu": "丁火", "geju": "正官格", "dayStrength": "中和",
        "sizhu": {"year": "甲寅", "month": "丁卯", "day": "丁酉", "hour": "癸卯"},
        "geJu": {"mainCandidate": {"name": "正官格", "shishen": "正官"}},
        "yongshenDetail": {"candidates": []},
    }
    hits = asyncio.run(service.retrieve_for_chart_compound(
        chart, kinds=["meta", "personality"],
        user_message="讲一下我的整体",
        index_root=mini_index, use_selector=False, final_k=8,
    ))
    files = {h["file"] for h in hits}
    # meta 轴: 主十神章 (lun-zheng-guan) 或 主十神泛论 (juan-04 论丁日含格局/调候)
    has_meta_axis = any(
        "lun-zheng-guan" in f or "guan-sha" in f
        or "juan-04" in f or "qiongtong-baojian" in f  # 调候层也是 meta 轴
        for f in files
    )
    # personality 轴: 性情章 / 干支体象
    has_persona_axis = any(
        "gan-zhi-ti-xiang" in f or "xing-qing" in f
        or "lun-shi-gan-pei-he" in f
        for f in files
    )
    assert has_meta_axis, f"compound 应包含 meta 轴材料, files={files}"
    assert has_persona_axis, f"compound 应包含 性情 轴材料, files={files}"
    # 两轴都进等于 compound 真的把跨域信息都拿到了 (单 policy 做不到)
    assert has_meta_axis and has_persona_axis, "compound 必须同时 cover 两轴"


def test_compound_retrieval_single_kind_falls_back_to_single(mini_index):
    """单 kind compound 应该和直接调 retrieve_for_chart 一致 — 没有
    冗余开销,语义和单 policy 检索完全等价。"""
    chart = _chart_jia_qisha()
    single = asyncio.run(service.retrieve_for_chart(
        chart, kind="relationship", user_message="婚姻怎么看",
        index_root=mini_index, use_selector=False, final_k=4,
    ))
    compound = asyncio.run(service.retrieve_for_chart_compound(
        chart, kinds=["relationship"], user_message="婚姻怎么看",
        index_root=mini_index, use_selector=False, final_k=4,
    ))
    assert [h["file"] for h in compound] == [h["file"] for h in single]


def test_compound_retrieval_dedupes_overlapping_candidates(mini_index):
    """同一 claim 在多个 policy 候选池都出现时,合并应该去重保留一份,
    score 取最高,不让重复 claim 占用 final K 名额。"""
    chart = _chart_jia_qisha()
    hits = asyncio.run(service.retrieve_for_chart_compound(
        chart, kinds=["meta", "verdict"],  # 都覆盖 七杀格 / 论用神成败
        user_message="这盘成败",
        index_root=mini_index, use_selector=False, final_k=8,
    ))
    seen_files_scopes = [(h["file"], h["scope"]) for h in hits]
    assert len(seen_files_scopes) == len(set(seen_files_scopes)), (
        f"compound 不应有重复 (file,scope), 实际: {seen_files_scopes}"
    )


def test_persona_retrieval_pulls_diverse_sources(mini_index):
    """persona 检索不能被 xing-qing 一章独占。命理上"古书定调·画像"
    真正的 3 个核心来源:
      1. 滴天髓·性情章 (直断: "五气不戾,性情中和")
      2. 子平真诠 04 论十干配合性情
      3. 渊海子平 04 干支体象 ("丁火其形一烛灯") ← 之前 persona allowed
         里没列这个章,完全召不到,是 review 发现的最关键漏洞
    required_domains 把 xing-qing 整章非性情段过滤掉,腾出名额给
    其它两个来源。"""
    chart = {
        "rizhu": "丁火", "geju": "正官格", "dayStrength": "中和",
        "sizhu": {"year": "甲寅", "month": "丁卯", "day": "丁酉", "hour": "癸卯"},
        "geJu": {"mainCandidate": {"name": "正官格", "shishen": "正官"}},
        "yongshenDetail": {"candidates": []},
    }
    hits = asyncio.run(service.retrieve_for_chart(
        chart, kind="persona", user_message="这盘什么性格",
        index_root=mini_index, use_selector=False, final_k=6,
    ))
    files = {h["file"] for h in hits}
    # 至少应该见到 3 个不同来源
    assert len(files) >= 3, f"persona 应交叉 ≥3 个来源,实际 files={files}"
    # 关键: 干支体象 必须在召回里 (这是 review 发现的最大漏洞)
    has_gan_zhi_ti_xiang = any("gan-zhi-ti-xiang" in f for f in files)
    assert has_gan_zhi_ti_xiang, (
        f"persona 必须召回 渊海子平 干支体象 (命理上'X日如X火'画像核心),"
        f"实际 files={files}"
    )


def test_meta_zheng_guan_chart_uses_correct_chapters(mini_index):
    """meta + 正官格 — 当前只对 七杀 有 special branch,正官落到 default
    policy 失去 ziping-zhenquan/31_lun-zheng-guan 的优先权。这个测试
    pin 住正官也得到对应的章节路由。"""
    chart = {
        "rizhu": "丁火", "geju": "正官格", "dayStrength": "中和",
        "sizhu": {"year": "甲寅", "month": "丁卯", "day": "丁酉", "hour": "癸卯"},
        "geJu": {"mainCandidate": {"name": "正官格", "shishen": "正官"}},
        "yongshenDetail": {"candidates": [{"method": "格局", "name": "正官"}]},
    }
    hits = asyncio.run(service.retrieve_for_chart(
        chart, kind="meta", user_message="正官格怎么看",
        index_root=mini_index, use_selector=False, final_k=6,
    ))
    files = [h["file"] for h in hits]
    # 正官格应该能见到 论正官 章
    has_zhenguan = any(
        "lun-zheng-guan" in f or "zheng-guan-pian-guan" in f for f in files
    )
    assert has_zhenguan, f"正官格 meta 应召回 论正官 章,实际 files: {files}"


def test_wealth_prefers_wealth_authority_over_generic_verse(mini_index):
    chart = {
        "rizhu": "戊土", "geju": "正财格", "dayStrength": "身强",
        "sizhu": {"year": "甲子", "month": "癸亥", "day": "戊午", "hour": "庚申"},
        "geJu": {"mainCandidate": {"shishen": "正财"}},
        "yongshenDetail": {"candidates": [{"method": "扶抑", "name": "财"}]},
    }
    hits = asyncio.run(service.retrieve_for_chart(
        chart, kind="section:wealth", user_message="我的财运和赚钱方式怎么看",
        index_root=mini_index, use_selector=False, final_k=4,
    ))
    assert hits[0]["file"] == "ditian-sui/liu-qin-lun_05_he-zhi-zhang.md"
    assert all("juan-12" not in h["file"] for h in hits[:3])


def test_wealth_keeps_specific_sanming_day_hour_anchor(mini_index):
    hits = asyncio.run(service.retrieve_for_chart(
        _chart_jia_shen_qisha(), kind="section:wealth",
        user_message="我的财运怎么样",
        index_root=mini_index, use_selector=False, final_k=6,
    ))

    anchor_hits = [
        h for h in hits
        if h["file"] == "sanming-tonghui/juan-08.md"
        and h["scope"] == "六甲日戊辰時斷"
    ]
    assert anchor_hits, "甲戌日戊辰时的财运问题必须保留三命通会日时诀文"
    assert len(anchor_hits) >= 2
    assert hits[0]["file"] == "sanming-tonghui/juan-08.md"
    assert "甲戌日戊辰时大富" in hits[0]["text"]
    assert any("天财坐库" in h["text"] for h in anchor_hits)
    assert any("甲戌日戊辰时大富" in h["text"] for h in anchor_hits)


def test_selector_path_keeps_specific_sanming_day_hour_anchor_first(mini_index):
    hits = asyncio.run(service.retrieve_for_chart(
        _chart_jia_shen_qisha(), kind="section:wealth",
        user_message="我的财运怎么样",
        index_root=mini_index, use_selector=True, final_k=6,
    ))
    assert hits[0]["file"] == "sanming-tonghui/juan-08.md"
    assert hits[0]["scope"] == "六甲日戊辰時斷"
    assert "甲戌日戊辰时大富" in hits[0]["text"]


def test_liunian_prefers_xingyun_authority(mini_index):
    hits = asyncio.run(service.retrieve_for_chart(
        _chart_jia_qisha(), kind="liunian", user_message="今年流年要注意什么",
        index_root=mini_index, use_selector=False, final_k=3,
    ))
    assert hits[0]["file"] == "ziping-zhenquan/25_lun-xing-yun.md"
    assert all("gan-zhi-zong-lun" not in h["file"] for h in hits)


def test_tiaohou_prefers_matching_qiongtong_day_and_month(mini_index):
    chart = {
        "rizhu": "壬水", "geju": "建禄格", "dayStrength": "身强",
        "sizhu": {"year": "癸亥", "month": "壬子", "day": "壬寅", "hour": "丙午"},
        "geJu": {"mainCandidate": {"shishen": "建禄"}},
        "yongshenDetail": {"candidates": [{"method": "调候", "name": "火"}]},
    }
    hits = asyncio.run(service.retrieve_for_chart(
        chart, kind="meta", user_message="冬天壬水调候用什么",
        index_root=mini_index, use_selector=False, final_k=3,
    ))
    assert hits[0]["file"] == "qiongtong-baojian/10_lun-ren-shui.md"
    assert all("juan-12" not in h["file"] for h in hits)


def test_meta_jia_shen_qisha_prefers_core_chart_authorities(mini_index):
    hits = asyncio.run(service.retrieve_for_chart(
        _chart_jia_shen_qisha(), kind="meta",
        index_root=mini_index, use_selector=False, final_k=6,
    ))
    first_files = [h["file"] for h in hits[:6]]
    first_text = "\n".join(h["text"] for h in hits[:6])
    assert any("七月甲木" in h["text"] for h in hits[:3])
    assert any("甲日申月" in h["text"] for h in hits[:4])
    assert "ziping-zhenquan/39_lun-pian-guan.md" in first_files
    assert "sanming-tonghui/juan-08.md" not in first_files
    assert "甲木生于卯月" not in first_text


def test_anchor_priority_combo_day_hour_beats_user_msg():
    """Regression for the 三命通会·六甲日戊辰時斷 disappearance.

    Setup: a 甲日戊辰時 chart asking about 财运. The intents include both
    a `combo.day_hour` BM25 anchor (specific to 甲日戊辰時) and a generic
    `user_msg` BM25 anchor ("我的财运怎么样"). With wealth policy's 4
    `preferred_files`, only ~2 slots remain for non-preferred hits — so
    if `user_msg` anchors are placed before `combo.day_hour` anchors,
    the day-hour-specific 三命通会 chunks get pushed out of the final K.

    The fix ensures combo.day_hour anchors come first in the candidate
    pool, so the day-hour catalog entry survives the preferred-files cut.
    """
    from app.retrieval2.service import _anchor_kind_rank, _is_bm25_anchor_kind

    # The kinds we care about: combo.day_hour ranks lower (= higher priority)
    # than user_msg.
    assert _is_bm25_anchor_kind("combo.day_hour")
    assert _is_bm25_anchor_kind("user_msg")
    assert _anchor_kind_rank("combo.day_hour") < _anchor_kind_rank("user_msg"), (
        "combo.day_hour must outrank user_msg, otherwise generic chat-message "
        "BM25 hits will displace specific 日时诀文 anchors from the final K"
    )
    # All other anchor kinds (combo.*, liu_qin.*, shen_sha.*) should also
    # rank above user_msg.
    for kind in ("combo.gan_xiang", "combo.nv_ming", "combo.current_yun",
                 "liu_qin.specific", "shen_sha.overview", "shen_sha.魁罡"):
        assert _anchor_kind_rank(kind) < _anchor_kind_rank("user_msg"), (
            f"specific anchor {kind!r} must outrank generic user_msg"
        )


def test_meta_jia_shen_qisha_reinserts_preferred_anchors(mini_index, monkeypatch):
    async def stub_select(chart, intents, user_msg, candidates, *, k=6,
                          max_candidates=30, timeout_seconds=20.0, policy_hint=""):
        from app.retrieval2.types import RetrievalHit
        picked = next(c for c in candidates if c.claim.id == "qt.甲.申月")
        return [RetrievalHit(claim=picked.claim, tags=picked.tags,
                             score=picked.fused_score, reason="stub")]

    monkeypatch.setattr("app.retrieval2.selector.select", stub_select)
    hits = asyncio.run(service.retrieve_for_chart(
        _chart_jia_shen_qisha(), kind="meta",
        index_root=mini_index, use_selector=True, final_k=6,
    ))
    files = [h["file"] for h in hits]
    assert "qiongtong-baojian/02_lun-jia-mu.md" in files
    assert "sanming-tonghui/juan-04.md" in files
    assert "ziping-zhenquan/39_lun-pian-guan.md" in files
