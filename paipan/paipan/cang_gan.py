"""地支藏干表。Port of paipan-engine/src/ming/cangGan.js.

Node source stores each zhi as an ordered list of ``{gan, weight, role}``
entries where ``role`` is one of ``本气`` / ``中气`` / ``余气``. Middle (中气)
and residual (余气) may be absent entirely (四仲月 only carry 本气; 四孟月
carry 本气 + 中气; 四库月 carry all three).

Node exports (every one ported here):
    CANG_GAN       — the full weighted table (preserved verbatim as private
                     ``_CANG_GAN_RAW``; read via ``get_cang_gan_weighted``).
    getBenQi(zhi)  — ``get_ben_qi`` (本气 only).
    getCangGan(zhi) — ``get_cang_gan`` **in Python is an adapter**: returns a
                     ``{main, middle, residual}`` dict per the Python spec
                     tests. The raw weighted list is available via
                     ``get_cang_gan_weighted`` (matches Node's ``getCangGan``).

Naming note: Node uses Chinese keys (``gan``/``weight``/``role``) inside each
entry. The Python-facing ``get_cang_gan`` transforms those to English keys
(``main``/``middle``/``residual``) for Python API consistency while the
internal table keeps Node's shape byte-for-byte.
"""
from __future__ import annotations

from typing import Optional, TypedDict


class CangGanEntry(TypedDict):
    """One hidden-stem entry as in the Node source."""

    gan: str
    weight: float
    role: str  # "本气" | "中气" | "余气"


class CangGan(TypedDict):
    """Python-facing summary: main / middle / residual stems."""

    main: str
    middle: Optional[str]
    residual: Optional[str]


# NOTE: ming/cangGan.js:12-41  全表逐格照抄 Node 源码（含权重与 role）
_CANG_GAN_RAW: dict[str, list[CangGanEntry]] = {
    # NOTE: ming/cangGan.js:13
    "子": [{"gan": "癸", "weight": 1.0, "role": "本气"}],
    # NOTE: ming/cangGan.js:14-16
    "丑": [
        {"gan": "己", "weight": 1.0, "role": "本气"},
        {"gan": "癸", "weight": 0.5, "role": "中气"},
        {"gan": "辛", "weight": 0.3, "role": "余气"},
    ],
    # NOTE: ming/cangGan.js:17-19
    "寅": [
        {"gan": "甲", "weight": 1.0, "role": "本气"},
        {"gan": "丙", "weight": 0.5, "role": "中气"},
        {"gan": "戊", "weight": 0.3, "role": "余气"},
    ],
    # NOTE: ming/cangGan.js:20
    "卯": [{"gan": "乙", "weight": 1.0, "role": "本气"}],
    # NOTE: ming/cangGan.js:21-23
    "辰": [
        {"gan": "戊", "weight": 1.0, "role": "本气"},
        {"gan": "乙", "weight": 0.5, "role": "中气"},
        {"gan": "癸", "weight": 0.3, "role": "余气"},
    ],
    # NOTE: ming/cangGan.js:24-26
    "巳": [
        {"gan": "丙", "weight": 1.0, "role": "本气"},
        {"gan": "戊", "weight": 0.5, "role": "中气"},
        {"gan": "庚", "weight": 0.3, "role": "余气"},
    ],
    # NOTE: ming/cangGan.js:27-28  （午只有本气+中气）
    "午": [
        {"gan": "丁", "weight": 1.0, "role": "本气"},
        {"gan": "己", "weight": 0.5, "role": "中气"},
    ],
    # NOTE: ming/cangGan.js:29-31
    "未": [
        {"gan": "己", "weight": 1.0, "role": "本气"},
        {"gan": "丁", "weight": 0.5, "role": "中气"},
        {"gan": "乙", "weight": 0.3, "role": "余气"},
    ],
    # NOTE: ming/cangGan.js:32-34
    "申": [
        {"gan": "庚", "weight": 1.0, "role": "本气"},
        {"gan": "壬", "weight": 0.5, "role": "中气"},
        {"gan": "戊", "weight": 0.3, "role": "余气"},
    ],
    # NOTE: ming/cangGan.js:35
    "酉": [{"gan": "辛", "weight": 1.0, "role": "本气"}],
    # NOTE: ming/cangGan.js:36-38
    "戌": [
        {"gan": "戊", "weight": 1.0, "role": "本气"},
        {"gan": "辛", "weight": 0.5, "role": "中气"},
        {"gan": "丁", "weight": 0.3, "role": "余气"},
    ],
    # NOTE: ming/cangGan.js:39-40  （亥只有本气+中气）
    "亥": [
        {"gan": "壬", "weight": 1.0, "role": "本气"},
        {"gan": "甲", "weight": 0.5, "role": "中气"},
    ],
}

# NOTE: ming/cangGan.js:44-46
def get_ben_qi(zhi: str) -> Optional[str]:
    """Return the 本气 (main) stem of ``zhi``, or ``None`` if unknown."""
    entries = _CANG_GAN_RAW.get(zhi)
    return entries[0]["gan"] if entries else None


# NOTE: ming/cangGan.js:49-51 (weighted list form — matches Node's export)
def get_cang_gan_weighted(zhi: str) -> list[CangGanEntry]:
    """Return the full weighted list of hidden stems for ``zhi``.

    Mirrors Node's ``getCangGan``: ordered list of ``{gan, weight, role}``
    dicts. Returns ``[]`` for unknown zhi (matching Node's ``|| []``).
    """
    entries = _CANG_GAN_RAW.get(zhi)
    if not entries:
        return []
    return [dict(e) for e in entries]  # type: ignore[misc]


def get_cang_gan(zhi: str) -> CangGan:
    """Return ``{main, middle, residual}`` for ``zhi``.

    Python-side adapter over Node's weighted list: 本气 → ``main``,
    中气 → ``middle``, 余气 → ``residual``. Missing 中气/余气 become ``None``.
    """
    entries = _CANG_GAN_RAW.get(zhi)
    if not entries:
        raise ValueError(f"invalid zhi: {zhi!r}")
    result: CangGan = {"main": "", "middle": None, "residual": None}
    for entry in entries:
        if entry["role"] == "本气":
            result["main"] = entry["gan"]
        elif entry["role"] == "中气":
            result["middle"] = entry["gan"]
        elif entry["role"] == "余气":
            result["residual"] = entry["gan"]
    return result
