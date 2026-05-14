# server/scripts/validate_cards_data.py
"""Validates server/app/data/cards/*.json for completeness and cross-reference consistency.
Run: python server/scripts/validate_cards_data.py
Exit 0 on success, 1 on any failure with details."""
from __future__ import annotations
import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "app" / "data" / "cards"
TEN_SHEN = {"比肩", "劫财", "食神", "伤官", "正财", "偏财", "正官", "七杀", "正印", "偏印"}
STATES = {"绽放", "蓄力"}
FIVE_CATEGORIES = {"极强", "身强", "中和", "身弱", "极弱"}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def load(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def main() -> None:
    types = load("types.json")
    formations = load("formations.json")
    subtags = load("subtags.json")
    thresholds = load("state_thresholds.json")

    # types.json
    if len(types) != 20:
        fail(f"types.json: expected 20, got {len(types)}")
    expected_ids = {f"{i:02d}" for i in range(1, 21)}
    if set(types.keys()) != expected_ids:
        fail(f"types.json: ids must be 01..20, got {sorted(types.keys())}")
    combos = set()
    cosmic_names = set()
    for tid, info in types.items():
        for key in ("id", "day_stem", "state", "cosmic_name", "base_name",
                    "one_liner", "personality_tag", "theme_color", "illustration"):
            if key not in info:
                fail(f"types.json[{tid}]: missing {key}")
        if info["state"] not in STATES:
            fail(f"types.json[{tid}]: invalid state {info['state']!r}")
        combos.add((info["day_stem"], info["state"]))
        cosmic_names.add(info["cosmic_name"])
    if len(combos) != 20:
        fail(f"types.json: duplicate day_stem×state combos, got {len(combos)}")

    # formations.json
    if set(formations.keys()) != TEN_SHEN:
        fail(f"formations.json: keys must be 10 十神, got {sorted(formations.keys())}")
    for ss, info in formations.items():
        if info.get("name") != ss:
            fail(f"formations.json[{ss}]: name mismatch")
        sf = info.get("suffixes", {})
        if set(sf.keys()) != STATES:
            fail(f"formations.json[{ss}]: suffixes keys must be {STATES}")
        for s, label in sf.items():
            if not label or not isinstance(label, str):
                fail(f"formations.json[{ss}].suffixes[{s}]: empty")
        gl = info.get("golden_lines", {})
        if set(gl.keys()) != STATES:
            fail(f"formations.json[{ss}]: golden_lines keys must be {STATES}")
        for s, line in gl.items():
            if not line or not isinstance(line, str):
                fail(f"formations.json[{ss}].golden_lines[{s}]: empty")

    # subtags.json
    if set(subtags.keys()) != cosmic_names:
        fail(f"subtags.json: outer keys must equal types.json cosmic_names. "
             f"Missing: {cosmic_names - set(subtags.keys())}, "
             f"Extra: {set(subtags.keys()) - cosmic_names}")
    for name, inner in subtags.items():
        if set(inner.keys()) != TEN_SHEN:
            fail(f"subtags.json[{name}]: inner keys must be 10 十神")
        for ss, tags in inner.items():
            if not isinstance(tags, list) or len(tags) != 3:
                fail(f"subtags.json[{name}][{ss}]: must have exactly 3 tags, got {tags!r}")
            for i, t in enumerate(tags):
                if not isinstance(t, str) or not t.strip():
                    fail(f"subtags.json[{name}][{ss}][{i}]: empty or non-string")

    # thresholds
    if set(thresholds["mapping"].keys()) != FIVE_CATEGORIES:
        fail(f"state_thresholds.json mapping keys must be {FIVE_CATEGORIES}")
    for cat, state in thresholds["mapping"].items():
        if state not in STATES:
            fail(f"state_thresholds.json mapping[{cat}]: invalid state {state!r}")

    print(f"OK: 20 types × 10 十神 = 200 combos validated. "
          f"All 4 files internally consistent.")


if __name__ == "__main__":
    main()
