"""/api/media/cover — fetch + cache covers for songs and movie cards.

Workflow:
  1. Hash (title, artist) → cache key
  2. If cache hit, return metadata immediately
  3. Else: movies first use the bundled poster index exported from the old
     movie-agent project; songs query iTunes Search API (free, no key).
  4. Download the artwork, extract dominant + secondary palette colors with
     colorthief, save to local cache directory, return metadata.

Cache lives in ``server/var/media-cache/`` — gitignored, regenerable.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

import httpx
from colorthief import ColorThief
from fastapi import APIRouter, HTTPException, Query
from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/media", tags=["media"])

_CACHE_DIR = Path(__file__).resolve().parents[2] / "var" / "media-cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_MOVIE_POSTER_FILE = Path(__file__).resolve().parents[1] / "data" / "media" / "movie_posters.json"

_INDEX_FILE = _CACHE_DIR / "index.json"
_INDEX_LOCK = asyncio.Lock()


def _normalise_movie_key(value: str | None) -> str:
    value = (value or "").strip().lower()
    return re.sub(r"[\s\u3000《》〈〉「」『』“”\"'’‘·・:：\-—_（）()【】\[\]{}.,，。!！?？/\\]+", "", value)


def _load_movie_poster_cache() -> dict[str, list[dict[str, Any]]]:
    if not _MOVIE_POSTER_FILE.exists():
        return {}
    try:
        raw = json.loads(_MOVIE_POSTER_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — cache is best-effort
        logger.warning("movie poster cache unavailable: %r", exc)
        return {}

    rows = raw.values() if isinstance(raw, dict) else raw
    cache: dict[str, list[dict[str, Any]]] = {}

    def add_key(key: str, entry: dict[str, Any]) -> None:
        norm = _normalise_movie_key(key)
        if norm:
            cache.setdefault(norm, []).append(entry)

    for item in rows:
        if not isinstance(item, dict):
            continue
        if not item.get("poster_url"):
            continue
        add_key(str(item.get("title") or ""), item)
        for alias in item.get("aliases") or []:
            add_key(str(alias), item)

    source_rank = {
        "tmdb-curated-search": 0,
        "movie_agent_neo4j": 1,
        "tmdb-top-rated": 2,
        "tmdb-popular": 3,
    }
    for entries in cache.values():
        entries.sort(
            key=lambda e: (
                source_rank.get(str(e.get("source") or ""), 9),
                -(float(e.get("rating") or 0)),
            )
        )
    return cache


_MOVIE_POSTER_CACHE = _load_movie_poster_cache()


def _load_index() -> dict[str, dict[str, Any]]:
    if not _INDEX_FILE.exists():
        return {}
    try:
        with _INDEX_FILE.open(encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:  # noqa: BLE001 — corrupt cache → start fresh
        logger.warning("media cache index corrupt, resetting")
        return {}


def _save_index(idx: dict[str, dict[str, Any]]) -> None:
    tmp = _INDEX_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(idx, fh, ensure_ascii=False)
    tmp.replace(_INDEX_FILE)


def _key(kind: str, title: str, artist: str | None) -> str:
    h = hashlib.md5(f"{kind}|{title}|{artist or ''}".encode("utf-8"))
    return h.hexdigest()


def _hex(rgb: tuple[int, int, int] | None) -> str:
    if not rgb:
        return ""
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"


async def _itunes_search(
    title: str,
    extra: str | None = None,
    *,
    entity: Literal["song", "movie"] = "song",
) -> dict[str, Any] | None:
    """Return ``{ url, year? }`` for the best-match iTunes hit.

    ``country=CN`` 第一次试；零结果时回退到 ``US``。中文电影名（"黑天鹅"
    / "盗梦空间" 之类）在 CN store 几乎全 0，但海报数据本身在 US store 里
    用相同查询字符串能拿到（iTunes 跨区搜索是按 term 全文匹配，不强制
    本地化结果集）。两个 country 都空才返 None。
    """
    term = f"{title} {extra}" if extra else title
    countries = ("CN", "US")
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as cli:
            for country in countries:
                params = {
                    "term": term,
                    "entity": entity,
                    "limit": "3",
                    "country": country,
                }
                r = await cli.get("https://itunes.apple.com/search", params=params)
                if r.status_code != 200:
                    continue
                data = r.json()
                results = data.get("results") or []
                if not results:
                    continue
                best = results[0]
                url = best.get("artworkUrl100")
                if not url:
                    continue
                year = ""
                release = best.get("releaseDate") or ""
                if isinstance(release, str) and len(release) >= 4 and release[:4].isdigit():
                    year = release[:4]
                return {"url": url, "year": year}
    except Exception as exc:  # noqa: BLE001
        logger.warning("iTunes search failed for %r entity=%s: %r", term, entity, exc)
    return None


async def _tmdb_search_movie(title: str) -> dict[str, Any] | None:
    """Search TMDB for a movie and return ``{ url, year? }``. Tries zh-CN
    first; if zero results, retries with no language hint so English /
    Japanese / Korean originals still match. Returns None if no API key
    is configured or TMDB fails / returns nothing."""
    key = settings.tmdb_api_key
    if not key:
        # 没配 key 时电影几乎拿不到封面 — iTunes Movies 中文片源覆盖率
        # 极差。把这个状态显式打到日志，避免运维盯着 404 找半天。
        logger.warning(
            "TMDB_API_KEY not configured — movie covers will fall back to "
            "iTunes (poor 中文 coverage). Get a free key at "
            "https://www.themoviedb.org/settings/api"
        )
        return None
    try:
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as cli:
            for lang in ("zh-CN", None):
                params: dict[str, Any] = {
                    "api_key": key,
                    "query": title,
                    "include_adult": "false",
                }
                if lang:
                    params["language"] = lang
                r = await cli.get(
                    "https://api.themoviedb.org/3/search/movie",
                    params=params,
                )
                if r.status_code != 200:
                    continue
                data = r.json()
                results = data.get("results") or []
                if not results:
                    continue
                best = results[0]
                poster_path = best.get("poster_path")
                if not poster_path:
                    continue
                # w500 is high-enough for our 600x600 normalize step.
                url = f"https://image.tmdb.org/t/p/w500{poster_path}"
                year = ""
                release = best.get("release_date") or ""
                if isinstance(release, str) and len(release) >= 4 and release[:4].isdigit():
                    year = release[:4]
                return {"url": url, "year": year}
    except Exception as exc:  # noqa: BLE001
        logger.warning("TMDB search failed for %r: %r", title, exc)
    return None


def _lookup_movie_poster_cache(title: str, extra: str | None = None) -> dict[str, Any] | None:
    """Return cached TMDB poster metadata from the bundled movie-agent export."""
    norm_title = _normalise_movie_key(title)
    if not norm_title:
        return None

    cache_entry = _MOVIE_POSTER_CACHE.get(title) or _MOVIE_POSTER_CACHE.get(norm_title)
    if not cache_entry:
        return None

    entries = cache_entry if isinstance(cache_entry, list) else [cache_entry]
    norm_extra = _normalise_movie_key(extra)
    chosen = entries[0]
    if norm_extra:
        for entry in entries:
            directors = "".join(str(d) for d in (entry.get("directors") or []))
            if norm_extra and norm_extra in _normalise_movie_key(directors):
                chosen = entry
                break
            if norm_extra == _normalise_movie_key(entry.get("year")):
                chosen = entry
                break

    url = chosen.get("poster_url") or chosen.get("url")
    if not url:
        return None
    release = str(chosen.get("release_date") or "")
    year = str(chosen.get("year") or "")
    if not year and len(release) >= 4 and release[:4].isdigit():
        year = release[:4]
    return {"url": url, "year": year}


async def _download(url: str) -> bytes | None:
    """Download cover bytes. For iTunes URLs, upgrade artworkUrl100 → 300x300.
    TMDB URLs are passed through unchanged (we ask for w500 already)."""
    candidates = [url]
    if "100x100bb." in url:
        candidates.insert(
            0,
            url.replace("100x100bb.jpg", "300x300bb.jpg").replace(
                "100x100bb.png", "300x300bb.png",
            ),
        )
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as cli:
            for u in candidates:
                r = await cli.get(u)
                if r.status_code == 200 and r.content:
                    return r.content
    except Exception as exc:  # noqa: BLE001
        logger.warning("cover download failed for %s: %r", url, exc)
    return None


def _normalise_image(raw: bytes, dest: Path) -> None:
    """Write a JPEG with sane dimensions, regardless of source encoding."""
    img = Image.open(BytesIO(raw)).convert("RGB")
    if max(img.size) > 600:
        img.thumbnail((600, 600), Image.LANCZOS)
    img.save(dest, "JPEG", quality=88, optimize=True)


def _palette_for(path: Path) -> tuple[str, str]:
    """Pick dominant + secondary hex colors from the saved image.
    Falls back to a neutral cool gradient on any extraction failure."""
    try:
        ct = ColorThief(str(path))
        dominant = ct.get_color(quality=2)
        palette = ct.get_palette(color_count=3, quality=2)
        secondary = next(
            (c for c in palette if c != dominant),
            dominant,
        )
        return _hex(dominant), _hex(secondary)
    except Exception as exc:  # noqa: BLE001
        logger.warning("colorthief failed on %s: %r", path, exc)
        return "#3a4d6f", "#7b9ec5"


def _entry_response(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "url": f"/static/media-cache/{entry['filename']}",
        "dominantHex": entry.get("dominantHex"),
        "secondaryHex": entry.get("secondaryHex"),
        "year": entry.get("year") or None,
    }


async def _resolve_artwork(kind: str, title: str, extra: str) -> dict[str, Any] | None:
    """Pick the best upstream source for the kind. Returns ``{ url, year? }``
    or None if no source has the cover."""
    if kind == "song":
        return await _itunes_search(title, extra, entity="song")
    if kind == "movie":
        cached = _lookup_movie_poster_cache(title, extra)
        if cached:
            return cached
        # Try TMDB first (zh-CN coverage is solid); fall back to iTunes Movies.
        tmdb = await _tmdb_search_movie(title)
        if tmdb:
            return tmdb
        return await _itunes_search(title, extra, entity="movie")
    return None


@router.get("/cover")
async def get_cover(
    type: Literal["song", "movie"] = Query(..., description="media kind"),
    title: str = Query(..., min_length=1, max_length=120),
    artist: str | None = Query(None, max_length=120),
) -> dict[str, Any]:
    """Return ``{ url, dominantHex, secondaryHex, year? }`` for a media cover.

    ``artist`` is the disambiguation hint — for songs it's the artist name,
    for movies it's the director (used as a search hint when present).
    Books rely on the icon-only frontend fallback (no upstream source covers
    Chinese books reliably).
    """
    if type not in ("song", "movie"):
        raise HTTPException(status_code=400, detail="cover type not supported")

    title = title.strip()
    extra = (artist or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title required")

    key = _key(type, title, extra)

    # Read-side cache hit (no lock — index is read-only here).
    index = _load_index()
    entry = index.get(key)
    if entry and (Path(_CACHE_DIR / entry["filename"]).exists()):
        return _entry_response(entry)

    # Miss — fetch + extract under a lock to avoid duplicate writes for the
    # same (kind, title, extra) tuple if two requests race in.
    async with _INDEX_LOCK:
        index = _load_index()
        entry = index.get(key)
        if entry and (Path(_CACHE_DIR / entry["filename"]).exists()):
            return _entry_response(entry)

        artwork = await _resolve_artwork(type, title, extra)
        if not artwork or not artwork.get("url"):
            raise HTTPException(status_code=404, detail="cover not found")
        raw = await _download(artwork["url"])
        if not raw:
            raise HTTPException(status_code=502, detail="cover download failed")

        filename = f"{key}.jpg"
        dest = _CACHE_DIR / filename
        try:
            _normalise_image(raw, dest)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cover normalise failed for %s: %r", title, exc)
            raise HTTPException(status_code=502, detail="cover encode failed")

        dominant, secondary = _palette_for(dest)
        index[key] = {
            "filename": filename,
            "dominantHex": dominant,
            "secondaryHex": secondary,
            "title": title,
            "artist": extra,
            "kind": type,
            "year": artwork.get("year") or "",
        }
        _save_index(index)

        return _entry_response(index[key])


__all__ = ["router"]
