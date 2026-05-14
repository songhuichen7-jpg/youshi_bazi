"""Build the retrieval2 index.

Three-phase pipeline:

    1. split   — md → ClaimUnit (deterministic, no network)
    2. tag     — DeepSeek 打标 (one network call per claim, async, ~5 min)
    3. bm25    — build inverted index (deterministic, ~5 sec)

Increments:
* If a chapter file's SHA-256 hasn't changed AND splitter/tagger versions
  are unchanged, reuse the existing claim+tag rows for that file.
* ``--rebuild`` ignores prior state and re-tags everything.

Usage::

    # Default (incremental; --no-tag for sandbox/CI without API key)
    PYTHONPATH=server python -m scripts.build_classics_index

    # Skip the LLM tag pass (use only what's on disk)
    PYTHONPATH=server python -m scripts.build_classics_index --no-tag

    # Force full rebuild
    PYTHONPATH=server python -m scripts.build_classics_index --rebuild

    # Time-bounded (process at most N claims this run, save partial progress)
    PYTHONPATH=server python -m scripts.build_classics_index --max-tag 500
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from collections import Counter
from pathlib import Path

from app.retrieval2 import storage
from app.retrieval2.bm25 import build_bm25, save_bm25
from app.retrieval2.splitter import iter_classics, split_chapter
from app.retrieval2.tagger import tag_all
from app.retrieval2.types import (
    INDEX_SCHEMA_VERSION,
    SPLITTER_VERSION,
    TAGGER_PROMPT_VERSION,
    ClaimTags,
    ClaimUnit,
)

logger = logging.getLogger("retrieval2.indexer")
DEFAULT_CLASSICS = Path(__file__).resolve().parents[2] / "classics"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "var" / "retrieval2"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--classics", type=Path, default=DEFAULT_CLASSICS)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--rebuild", action="store_true")
    p.add_argument("--no-tag", action="store_true",
                   help="Skip the LLM tag pass; reuse existing tags or leave empty.")
    p.add_argument("--max-tag", type=int, default=0,
                   help="Tag at most N claims this run (0 = no limit).")
    p.add_argument("--max-concurrency", type=int, default=32)
    p.add_argument("--limit-files", type=int, default=0,
                   help="If >0, only process the first N files (for smoke).")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )


def _load_prior(out_dir: Path, *, rebuild: bool):
    p = storage.paths(out_dir)
    if rebuild:
        return {}, {}, {}
    manifest = storage.load_manifest(p.manifest)
    if manifest is None:
        return {}, {}, {}
    if (
        manifest.get("schema_version") != INDEX_SCHEMA_VERSION
        or manifest.get("splitter_version") != SPLITTER_VERSION
    ):
        logger.info("schema/splitter version mismatch — full rebuild")
        return {}, {}, {}
    file_hashes = manifest.get("file_hashes") or {}
    claims = {c.id: c for c in storage.load_claims(p.claims)}
    tags = {t.claim_id: t for t in storage.load_tags(p.tags)}
    if manifest.get("tagger_prompt_version") != TAGGER_PROMPT_VERSION:
        logger.info("tagger prompt version mismatch — keeping claims, dropping tags")
        tags = {}
    return file_hashes, claims, tags


def _split_phase(args: argparse.Namespace, *, prior_hashes: dict[str, str],
                 prior_claims: dict[str, ClaimUnit]
                 ) -> tuple[list[ClaimUnit], dict[str, str]]:
    classics_root = args.classics.resolve()
    file_hashes: dict[str, str] = {}
    out_claims: list[ClaimUnit] = []
    seen = 0
    for rel, raw in iter_classics(classics_root):
        seen += 1
        if args.limit_files and seen > args.limit_files:
            break
        sha = storage.file_sha256(classics_root / rel)
        file_hashes[rel] = sha
        unchanged = (not args.rebuild) and prior_hashes.get(rel) == sha
        if unchanged and prior_claims:
            kept = [c for c in prior_claims.values() if c.chapter_file == rel]
            out_claims.extend(kept)
            logger.debug("reuse %s (%d claims)", rel, len(kept))
        else:
            book = rel.split("/", 1)[0]
            chunks = split_chapter(book, rel, raw)
            out_claims.extend(chunks)
            logger.debug("split %s → %d claims", rel, len(chunks))
    return out_claims, file_hashes


async def _tag_phase(claims: list[ClaimUnit], prior_tags: dict[str, ClaimTags],
                     *, max_tag: int, concurrency: int,
                     checkpoint_path: Path | None = None,
                     checkpoint_every: int = 100,
                     ) -> dict[str, ClaimTags]:
    """Tag claims concurrently. Writes a checkpoint of accumulated tags
    every ``checkpoint_every`` completions so a Ctrl-C / kill -9 mid-run
    doesn't lose more than ~100 calls of work. Final write happens in
    main_async after all tags are gathered."""
    needed = [c for c in claims if c.id not in prior_tags]
    if max_tag and len(needed) > max_tag:
        needed = needed[:max_tag]
    if not needed:
        return prior_tags
    logger.info("tagging %d claims (concurrency=%d)", len(needed), concurrency)

    accumulated: dict[str, ClaimTags] = dict(prior_tags)
    completed = 0
    last_checkpoint = 0

    def on_progress(_idx: int, tag: ClaimTags) -> None:
        nonlocal completed, last_checkpoint
        accumulated[tag.claim_id] = tag
        completed += 1
        if checkpoint_path is not None and completed - last_checkpoint >= checkpoint_every:
            try:
                storage.write_tags(checkpoint_path, list(accumulated.values()))
                last_checkpoint = completed
                logger.info("checkpoint: %d / %d tags written",
                            len(accumulated), len(claims))
            except Exception as exc:  # noqa: BLE001
                logger.warning("checkpoint write failed: %s", exc)

    new_tags = await tag_all(
        needed, max_concurrency=concurrency, progress_callback=on_progress,
    )
    out = dict(prior_tags)
    for t in new_tags:
        out[t.claim_id] = t
    return out


def _stats(claims: list[ClaimUnit], tags: dict[str, ClaimTags]) -> dict:
    by_book = Counter(c.book for c in claims)
    by_kind = Counter(c.kind for c in claims)
    n_tagged = sum(1 for t in tags.values()
                   if t.shishen or t.yongshen_method or t.domain or t.geju)
    return {
        "claim_count": len(claims),
        "char_total": sum(len(c.text) for c in claims),
        "by_book": dict(by_book),
        "by_kind": dict(by_kind),
        "tagged_with_signal": n_tagged,
        "tag_coverage_pct": round(100 * n_tagged / max(1, len(claims)), 1),
    }


async def main_async(args: argparse.Namespace) -> int:
    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    p = storage.paths(out_dir)
    logger.info("classics_root=%s out_dir=%s", args.classics, out_dir)

    prior_hashes, prior_claims, prior_tags = _load_prior(out_dir, rebuild=args.rebuild)

    claims, file_hashes = _split_phase(
        args, prior_hashes=prior_hashes, prior_claims=prior_claims,
    )
    logger.info("split phase: %d claims across %d files",
                len(claims), len(file_hashes))

    storage.write_claims(p.claims, claims)

    if args.no_tag:
        tags = prior_tags
        logger.info("--no-tag: keeping prior %d tags", len(tags))
    else:
        tags = await _tag_phase(
            claims, prior_tags,
            max_tag=args.max_tag, concurrency=args.max_concurrency,
            checkpoint_path=p.tags,
            checkpoint_every=100,
        )

    storage.write_tags(p.tags, tags.values())
    save_bm25(build_bm25(claims), p.bm25)

    stats = _stats(claims, tags)
    storage.write_manifest(
        p.manifest,
        classics_root=args.classics.resolve(),
        file_hashes=file_hashes,
        stats=stats,
    )
    logger.info("manifest written: %s", p.manifest)
    logger.info("stats: %s", stats)
    return 0


def main() -> int:
    args = parse_args()
    _setup_logging(args.verbose)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
