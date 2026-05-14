"""Trace why 三命通会 wins ranking when more specific books exist.

Reproduces the test_relationship_prefers_spouse_not_children failure pattern
without going through pytest, so we can read score components directly.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.retrieval2 import (
    storage, build_bm25, save_bm25, build_kg, bazi_chart_to_intents,
    ClaimUnit, ClaimTags,
)
from app.retrieval2.policy import build_policy
from app.retrieval2 import service


def _build_mini_index(tmp_dir: Path):
    """Replica of the mini_index fixture in the failing tests (FULL set)."""
    claims = [
        ClaimUnit(id="zpzq.35.0007", book="ziping-zhenquan",
                  chapter_file="ziping-zhenquan/35_lun-yin-shou.md",
                  chapter_title="论印绶", section=None,
                  text="七杀重而身轻者宜印通关化煞，身轻印重则贵显。"
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
        ClaimTags(claim_id="zpzq.偏官", domain=("格局成败",), shishen=("七杀",),
                  day_strength=("身弱",), geju=("七杀格",), authority=0.95),
        ClaimTags(claim_id="dts.fuqi.1", domain=("六亲",), shishen=("正财",),
                  authority=0.95),
        ClaimTags(claim_id="dts.zinv.1", domain=("六亲",), shishen=("七杀", "正印"),
                  day_strength=("身轻",), authority=0.9),
        ClaimTags(claim_id="dts.hezhizhang.rich", domain=("财官",),
                  shishen=("正财", "食神"), day_strength=("身旺",), authority=0.95),
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
    ]
    p_claims = tmp_dir / "claims.jsonl"
    p_tags = tmp_dir / "tags.jsonl"
    p_bm25 = tmp_dir / "bm25.pkl"
    p_manifest = tmp_dir / "manifest.json"
    storage.write_claims(p_claims, claims)
    storage.write_tags(p_tags, tags)
    save_bm25(build_bm25(claims), p_bm25)
    storage.write_manifest(p_manifest, classics_root=Path("/no/such"),
                           file_hashes={}, stats={})
    return tmp_dir


def trace_test_wealth():
    """Repro test_wealth_prefers_wealth_authority_over_generic_verse."""
    chart = {
        "rizhu": "戊土", "geju": "正财格", "dayStrength": "身强",
        "sizhu": {"year": "甲子", "month": "癸亥", "day": "戊午", "hour": "庚申"},
        "geJu": {"mainCandidate": {"shishen": "正财"}},
        "yongshenDetail": {"candidates": [{"method": "扶抑", "name": "财"}]},
    }
    kind = "section:wealth"
    user_msg = "我的财运和赚钱方式怎么看"

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        idx_dir = _build_mini_index(Path(td))

        # Get policy
        pol = build_policy(chart, kind, user_msg)
        print("=== POLICY ===")
        print(f"  kind={pol.kind}")
        print(f"  preferred_books={pol.preferred_books}")
        print(f"  preferred_files={pol.preferred_files}")
        print(f"  preferred_file_fragments={pol.preferred_file_fragments}")
        print(f"  rejected_file_fragments={pol.rejected_file_fragments}")
        print(f"  required_domains={pol.required_domains}")
        print(f"  positive_domains={pol.positive_domains}")
        print(f"  day_gan={pol.day_gan!r}, month_zhi={pol.month_zhi!r}, season={pol.season!r}")
        print(f"  term_boosts={pol.term_boosts}")

        # Get intents
        intents = bazi_chart_to_intents(chart, kind, user_msg)
        print()
        print("=== INTENTS ===")
        for i in intents:
            print(f"  · {i}")

        # Run retrieval
        hits = asyncio.run(service.retrieve_for_chart(
            chart, kind=kind, user_message=user_msg,
            index_root=idx_dir, use_selector=False, final_k=10,
        ))
        print()
        print("=== TOP HITS (use_selector=False, top fused) ===")
        for h in hits[:8]:
            print(f"  · {h['file']:<60} score={h.get('score', 'n/a')}")

        # Compute boost for each claim — bundle is a tuple, unpack it
        print()
        print("=== POLICY BOOST PER CLAIM ===")
        b = service._bundle(str(idx_dir))
        # Best-effort: probe the bundle shape
        from app.retrieval2 import storage as _storage
        # Re-load tags + claims directly to inspect
        import json as _j
        claim_lookup = {}
        for line in (idx_dir / "claims.jsonl").read_text(encoding="utf-8").splitlines():
            d = _j.loads(line)
            claim_lookup[d["id"]] = ClaimUnit(**d)
        tag_lookup = {}
        for line in (idx_dir / "tags.jsonl").read_text(encoding="utf-8").splitlines():
            d = _j.loads(line)
            tag_lookup[d["claim_id"]] = ClaimTags(**d)
        for cid, claim in claim_lookup.items():
            tags = tag_lookup.get(cid)
            if tags is None:
                continue
            rejected = pol.rejects(claim, tags)
            boost = pol.boost(claim, tags) if not rejected else None
            print(f"  · {cid:<22}  file={claim.chapter_file:<55}  reject={str(rejected):<5}  boost={boost}")


if __name__ == "__main__":
    trace_test_wealth()
