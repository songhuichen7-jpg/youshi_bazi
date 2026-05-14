"""City name → coordinates lookup. Ported from paipan-engine/src/cities.js.

Strategy (in order):
  1. Exact match on the raw (trimmed) input.
  2. Normalize (strip administrative suffix twice) then exact match.
  3. Fuzzy substring match (input contains known key, or key contains input),
     only for inputs of length >= 2, to avoid single-char false positives.

Real-solar-time correction only needs longitude; 0.1° ≈ 24s — the two-decimal
coordinates in the dataset are plenty.
"""
from __future__ import annotations
import json
import pathlib
import re
from functools import lru_cache
from typing import Optional

from paipan.types import City

_DATA_PATH = pathlib.Path(__file__).parent / "cities-data.json"


# NOTE: cities.js:29-56 — overseas supplement (pyecharts dataset is mainland-heavy).
# Same [lng, lat] shape as the raw JSON; overrides RAW on conflict.
_OVERSEAS: dict[str, list[float]] = {
    # 北美
    "纽约": [-74.006, 40.7128],
    "旧金山": [-122.4194, 37.7749],
    "洛杉矶": [-118.2437, 34.0522],
    "西雅图": [-122.3321, 47.6062],
    "波士顿": [-71.0589, 42.3601],
    "芝加哥": [-87.6298, 41.8781],
    "华盛顿": [-77.0369, 38.9072],
    "多伦多": [-79.3832, 43.6532],
    "温哥华": [-123.1207, 49.2827],
    "蒙特利尔": [-73.5673, 45.5017],
    # 欧洲
    "伦敦": [-0.1276, 51.5074],
    "巴黎": [2.3522, 48.8566],
    "柏林": [13.4050, 52.5200],
    "莫斯科": [37.6173, 55.7558],
    # 亚太 / 邻近
    "新加坡": [103.8198, 1.3521],
    "吉隆坡": [101.6869, 3.1390],
    "曼谷": [100.5018, 13.7563],
    "首尔": [126.9780, 37.5665],
    "东京": [139.6917, 35.6895],
    "大阪": [135.5023, 34.6937],
    "悉尼": [151.2093, -33.8688],
    "墨尔本": [144.9631, -37.8136],
    "奥克兰": [174.7633, -36.8485],
}


# NOTE: cities.js:61-68 — suffix list ordered long→short so "特别行政区"
# is tried before "区".
_SUFFIXES: list[str] = [
    "维吾尔自治区", "回族自治区", "壮族自治区", "特别行政区",
    "藏族自治州", "彝族自治州", "白族自治州", "苗族自治州", "回族自治州",
    "土家族苗族自治州", "苗族土家族自治州", "布依族苗族自治州", "哈尼族彝族自治州",
    "自治区", "自治州", "自治县", "自治旗",
    "地区", "林区", "矿区", "新区",
    "省", "市", "区", "县", "盟", "旗",
]

_WHITESPACE_RE = re.compile(r"\s+")
# NOTE: cities.js:103 — admin-suffix regex used to break ties in NORM_MAP.
_ADMIN_SUFFIX_RE = re.compile(r"[市县区旗州盟]$")


def _strip_suffix(s: str) -> str:
    # NOTE: cities.js:70-77
    for suf in _SUFFIXES:
        if len(s) > len(suf) and s.endswith(suf):
            return s[: -len(suf)]
    return s


def _normalize(raw: Optional[str]) -> str:
    # NOTE: cities.js:79-86
    if not raw:
        return ""
    s = _WHITESPACE_RE.sub("", str(raw).strip())
    # 连续剥两次，处理 "XX市辖区" 这种
    s = _strip_suffix(s)
    s = _strip_suffix(s)
    return s


class _Index:
    """Holds EXACT_MAP and NORM_MAP, equivalent to cities.js module-level state."""

    __slots__ = ("exact", "norm")

    def __init__(self) -> None:
        # name → (lng, lat)
        self.exact: dict[str, tuple[float, float]] = {}
        # normalized name → (lng, lat, canonical)
        self.norm: dict[str, tuple[float, float, str]] = {}


@lru_cache(maxsize=1)
def _build_index() -> _Index:
    """Load and index cities. Runs once per process."""
    # NOTE: cities.js:20-25 — load RAW; tolerate missing file.
    try:
        raw: dict[str, list[float]] = json.loads(
            _DATA_PATH.read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        raw = {}

    # NOTE: cities.js:58 — Object.assign(RAW, OVERSEAS): overseas overrides RAW.
    merged: dict[str, list[float]] = dict(raw)
    merged.update(_OVERSEAS)

    idx = _Index()
    # NOTE: cities.js:92-108 — buildIndex()
    for name, coords in merged.items():
        if not isinstance(coords, list) or len(coords) < 2:
            continue
        try:
            lng = float(coords[0])
            lat = float(coords[1])
        except (TypeError, ValueError):
            continue
        # JSON doesn't produce NaN/inf from standard dumps, but mirror the JS guard.
        if not (lng == lng and lat == lat):  # NaN check
            continue
        idx.exact[name] = (lng, lat)
        n = _normalize(name)
        if not n:
            continue
        # 冲突时偏向原名带 市/县/区 的条目（这些通常是标准行政名）
        prev = idx.norm.get(n)
        is_admin = bool(_ADMIN_SUFFIX_RE.search(name))
        if prev is None or is_admin:
            idx.norm[n] = (lng, lat, name)
    return idx


def get_city_coords(raw: Optional[str]) -> Optional[City]:
    """Resolve a user-entered city name to {lng, lat, canonical}.

    Returns None if not found. Ported from cities.js:117-151.
    """
    # NOTE: cities.js:118-120
    if not raw:
        return None
    s = _WHITESPACE_RE.sub("", str(raw).strip())
    if not s:
        return None

    idx = _build_index()

    # NOTE: cities.js:123-126 — 1. exact
    if s in idx.exact:
        lng, lat = idx.exact[s]
        return City(lng=lng, lat=lat, canonical=s)

    # NOTE: cities.js:129-130 — 2. normalized
    n = _normalize(s)
    if n and n in idx.norm:
        lng, lat, canonical = idx.norm[n]
        return City(lng=lng, lat=lat, canonical=canonical)

    # NOTE: cities.js:132-148 — 3. fuzzy substring (bidirectional), len >= 2 only
    if n and len(n) >= 2:
        # 先找 "输入包含已知key"（如 "湖南长沙" 包含 "长沙"）——偏向较长的key
        best_key: Optional[str] = None
        best_val: Optional[tuple[float, float, str]] = None
        for key, val in idx.norm.items():
            if len(key) < 2:
                continue
            if key in n and (best_key is None or len(key) > len(best_key)):
                best_key = key
                best_val = val
        if best_val is not None:
            lng, lat, canonical = best_val
            return City(lng=lng, lat=lat, canonical=canonical)

        # 再找 "已知key包含输入"（如输入 "浦东" 匹配到 "浦东新区"）
        for key, val in idx.norm.items():
            if n in key:
                lng, lat, canonical = val
                return City(lng=lng, lat=lat, canonical=canonical)

    return None


def all_cities() -> list[tuple[str, float, float]]:
    """Return every canonical (name, lng, lat) known to paipan.

    Name-sorted for stable hashing / ETag. Includes mainland dataset from
    cities-data.json plus the _OVERSEAS supplement. Server exposes this
    via GET /api/cities.
    """
    # NOTE: reuse the already-cached index built by _build_index(); the
    # exact map's keys are canonical names.
    idx = _build_index()
    return sorted(
        [(name, lng, lat) for name, (lng, lat) in idx.exact.items()],
        key=lambda t: t[0],
    )
