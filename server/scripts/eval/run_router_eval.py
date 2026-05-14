"""Run router eval against the LLM-based classifier.

Tests `app.prompts.router.build_messages` + `chat_once_with_fallback` +
`parse_router_json` directly,跳过 DB logging。每条 seed case 计算:

* primary_correct: bool
* secondary_recall: |expected ∩ predicted| / |expected| (or 1 if expected==∅)
* secondary_precision: |expected ∩ predicted| / |predicted| (or 1 if predicted==∅)
* secondary_extra: 多召回的 secondary intent 数量

聚合:
* overall primary accuracy
* per-difficulty primary accuracy
* per-failure-pattern primary accuracy
* secondary F1
* confusion matrix (primary)

Usage::
    PYTHONPATH=server uv run python -m scripts.eval.run_router_eval
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.llm.client import chat_once_with_fallback
from app.prompts.router import build_messages, parse_router_json
from app.services.exceptions import UpstreamLLMError

from scripts.eval.router_seed import SEEDS

REPO_ROOT = Path("/Users/veko/code/usual/bazi-analysis")
OUT_DIR = REPO_ROOT / "server" / "var" / "eval"

logger = logging.getLogger("eval.router")


@dataclass
class CaseResult:
    idx: int
    message: str
    history_len: int
    difficulty: str
    failure_pattern: str
    expected_primary: str
    expected_secondary: list[str]
    predicted_primary: str
    predicted_secondary: list[str]
    primary_correct: bool
    secondary_recall: float
    secondary_precision: float
    secondary_extra: int
    error: str | None = None
    raw_reason: str = ""
    raw_focus: list[str] = field(default_factory=list)


async def run_one(seed: dict, *, idx: int) -> CaseResult:
    expected_secondary = sorted(set(seed.get("expected_secondary") or []))

    try:
        text, _model = await chat_once_with_fallback(
            messages=build_messages(
                history=seed.get("history") or [],
                user_message=seed["message"],
            ),
            tier="fast", temperature=0, max_tokens=1600,
            disable_thinking=True,
        )
    except UpstreamLLMError as e:
        return CaseResult(
            idx=idx, message=seed["message"],
            history_len=len(seed.get("history") or []),
            difficulty=seed.get("difficulty", "easy"),
            failure_pattern=seed.get("failure_pattern", ""),
            expected_primary=seed["expected_primary"],
            expected_secondary=expected_secondary,
            predicted_primary="",
            predicted_secondary=[],
            primary_correct=False,
            secondary_recall=0.0,
            secondary_precision=0.0,
            secondary_extra=0,
            error=f"{e.code}: {e.message}",
        )

    parsed = parse_router_json(text)
    pred_primary = parsed.get("intent") or "other"
    pred_sec_raw = parsed.get("secondary_intents") or []
    pred_secondary = sorted(set(s for s in pred_sec_raw if isinstance(s, str)))

    # primary
    primary_correct = pred_primary == seed["expected_primary"]

    # secondary set metrics — 期望集合是 "至少包含" 语义
    expected_set = set(expected_secondary)
    pred_set = set(pred_secondary)
    intersect = expected_set & pred_set
    if expected_set:
        secondary_recall = len(intersect) / len(expected_set)
    else:
        secondary_recall = 1.0
    if pred_set:
        secondary_precision = len(intersect) / len(pred_set)
    else:
        secondary_precision = 1.0
    secondary_extra = len(pred_set - expected_set)

    return CaseResult(
        idx=idx, message=seed["message"],
        history_len=len(seed.get("history") or []),
        difficulty=seed.get("difficulty", "easy"),
        failure_pattern=seed.get("failure_pattern", ""),
        expected_primary=seed["expected_primary"],
        expected_secondary=expected_secondary,
        predicted_primary=pred_primary,
        predicted_secondary=pred_secondary,
        primary_correct=primary_correct,
        secondary_recall=secondary_recall,
        secondary_precision=secondary_precision,
        secondary_extra=secondary_extra,
        raw_reason=str(parsed.get("reason") or ""),
        raw_focus=list((parsed.get("retrieval_plan") or {}).get("focus") or []),
    )


def aggregate(results: list[CaseResult]) -> dict[str, Any]:
    n = len(results)
    if n == 0:
        return {"total": 0}

    n_primary = sum(1 for r in results if r.primary_correct)
    n_errors = sum(1 for r in results if r.error)

    # secondary F1 (per-case, then averaged) — 排除 expected_secondary 为空的 case (推 1)
    cross_axis = [r for r in results if r.expected_secondary]
    if cross_axis:
        avg_sec_recall = sum(r.secondary_recall for r in cross_axis) / len(cross_axis)
        avg_sec_prec = sum(r.secondary_precision for r in cross_axis) / len(cross_axis)
        avg_sec_f1 = (
            2 * avg_sec_recall * avg_sec_prec / (avg_sec_recall + avg_sec_prec)
            if (avg_sec_recall + avg_sec_prec) > 0 else 0.0
        )
    else:
        avg_sec_recall = avg_sec_prec = avg_sec_f1 = 1.0

    # by difficulty
    by_diff: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        by_diff[r.difficulty].append(r)
    diff_stats = {
        d: {
            "n": len(rs),
            "primary_acc": round(sum(1 for r in rs if r.primary_correct) / len(rs), 3),
            "secondary_recall": round(
                sum(r.secondary_recall for r in rs if r.expected_secondary) /
                max(1, sum(1 for r in rs if r.expected_secondary)), 3,
            ) if any(r.expected_secondary for r in rs) else None,
        }
        for d, rs in by_diff.items()
    }

    # by failure pattern
    by_fp: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        if r.failure_pattern:
            by_fp[r.failure_pattern].append(r)
    fp_stats = {
        fp: {
            "n": len(rs),
            "primary_acc": round(sum(1 for r in rs if r.primary_correct) / len(rs), 3),
            "primary_misses": [
                {
                    "msg": r.message,
                    "expected": r.expected_primary,
                    "predicted": r.predicted_primary,
                }
                for r in rs if not r.primary_correct
            ],
        }
        for fp, rs in by_fp.items()
    }

    # primary confusion (predicted -> expected counts for misses only)
    confusion: Counter = Counter()
    for r in results:
        if r.primary_correct or r.error:
            continue
        confusion[(r.expected_primary, r.predicted_primary)] += 1

    # all primary misses
    misses = [
        {
            "message": r.message,
            "history_len": r.history_len,
            "difficulty": r.difficulty,
            "failure_pattern": r.failure_pattern,
            "expected": r.expected_primary,
            "predicted": r.predicted_primary,
            "expected_secondary": r.expected_secondary,
            "predicted_secondary": r.predicted_secondary,
            "reason": r.raw_reason,
        }
        for r in results if not r.primary_correct and not r.error
    ]

    return {
        "total": n,
        "errors": n_errors,
        "primary_accuracy": round(n_primary / n, 3),
        "secondary_recall_cross_axis": round(avg_sec_recall, 3),
        "secondary_precision_cross_axis": round(avg_sec_prec, 3),
        "secondary_f1_cross_axis": round(avg_sec_f1, 3),
        "n_cross_axis_cases": len(cross_axis),
        "by_difficulty": diff_stats,
        "by_failure_pattern": fp_stats,
        "primary_confusion_top": [
            {"expected": e, "predicted": p, "count": c}
            for (e, p), c in confusion.most_common(15)
        ],
        "primary_misses": misses,
    }


async def main_async(args: argparse.Namespace) -> int:
    seeds = SEEDS
    if args.limit:
        seeds = seeds[: args.limit]

    logger.info("running %d router eval cases", len(seeds))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results_path = OUT_DIR / "router_results.jsonl"
    summary_path = OUT_DIR / "router_summary.json"

    sem = asyncio.Semaphore(args.concurrency)
    results: list[CaseResult] = []

    async def task(idx: int, seed: dict) -> CaseResult:
        async with sem:
            return await run_one(seed, idx=idx)

    coros = [task(i, s) for i, s in enumerate(seeds)]
    for i, coro in enumerate(asyncio.as_completed(coros), 1):
        r = await coro
        results.append(r)
        if i % 10 == 0 or i == len(seeds):
            n_correct = sum(1 for x in results if x.primary_correct)
            logger.info("  %d/%d done  primary=%d/%d", i, len(seeds), n_correct, len(results))

    results.sort(key=lambda r: r.idx)
    with results_path.open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")

    summary = aggregate(results)
    summary["meta"] = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "concurrency": args.concurrency,
        "model_tier": "fast",
        "n_seeds": len(seeds),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info("wrote %s", results_path)
    logger.info("wrote %s", summary_path)

    print(json.dumps({k: v for k, v in summary.items() if k != "primary_misses"},
                     ensure_ascii=False, indent=2))
    print(f"\n=== {len(summary['primary_misses'])} primary misses logged in {results_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
