"""On-disk artifact I/O.

Layout::

    <root>/
      manifest.json    # versions + per-source SHA-256 + stats
      claims.jsonl     # one ClaimUnit per line
      tags.jsonl       # one ClaimTags per line
      bm25.pkl         # picklable BM25Index

JSONL is used (not parquet) so the index has zero new dependencies.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

from .types import (
    INDEX_SCHEMA_VERSION,
    SPLITTER_VERSION,
    TAGGER_PROMPT_VERSION,
    ClaimTags,
    ClaimUnit,
)


@dataclass(frozen=True, slots=True)
class Paths:
    root: Path
    manifest: Path
    claims: Path
    tags: Path
    bm25: Path


def paths(root: Path) -> Paths:
    return Paths(
        root=root,
        manifest=root / "manifest.json",
        claims=root / "claims.jsonl",
        tags=root / "tags.jsonl",
        bm25=root / "bm25.pkl",
    )


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_claims(path: Path, claims: Iterable[ClaimUnit]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for c in claims:
            fh.write(json.dumps(c.to_dict(), ensure_ascii=False))
            fh.write("\n")
            n += 1
    return n


def load_claims(path: Path) -> Iterator[ClaimUnit]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield ClaimUnit.from_dict(json.loads(line))


def write_tags(path: Path, tags: Iterable[ClaimTags]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for t in tags:
            fh.write(json.dumps(t.to_dict(), ensure_ascii=False))
            fh.write("\n")
            n += 1
    return n


def load_tags(path: Path) -> Iterator[ClaimTags]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield ClaimTags.from_dict(json.loads(line))


def write_manifest(
    path: Path,
    *,
    classics_root: Path,
    file_hashes: dict[str, str],
    stats: dict[str, Any] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "splitter_version": SPLITTER_VERSION,
        "tagger_prompt_version": TAGGER_PROMPT_VERSION,
        "built_at": _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "classics_root": str(classics_root),
        "file_hashes": file_hashes,
        "stats": stats or {},
    }
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)


def load_manifest(path: Path) -> dict | None:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


__all__ = [
    "Paths",
    "paths",
    "file_sha256",
    "write_claims",
    "load_claims",
    "write_tags",
    "load_tags",
    "write_manifest",
    "load_manifest",
]
