"""
Deep equality diff with float tolerance, for oracle regression testing.

Returns a list of DiffEntry; empty list means equal.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass
class DiffEntry:
    path: str
    actual: Any
    expected: Any
    reason: str


def deep_diff(actual: Any, expected: Any, *,
              float_tolerance: float = 1e-9,
              path: str = "") -> list[DiffEntry]:
    """Recursively compare two values; return list of differences."""
    diffs: list[DiffEntry] = []

    # Type difference (except numeric int/float)
    if type(actual) is not type(expected):
        if not (isinstance(actual, (int, float)) and isinstance(expected, (int, float))):
            diffs.append(DiffEntry(
                path or "<root>", actual, expected,
                f"type mismatch: {type(actual).__name__} vs {type(expected).__name__}",
            ))
            return diffs

    if isinstance(actual, dict):
        assert isinstance(expected, dict)
        for key in sorted(set(actual) | set(expected)):
            sub_path = f"{path}.{key}" if path else key
            if key not in expected:
                diffs.append(DiffEntry(sub_path, actual[key], None, "unexpected key (not in expected)"))
            elif key not in actual:
                diffs.append(DiffEntry(sub_path, None, expected[key], "missing key"))
            else:
                diffs.extend(deep_diff(actual[key], expected[key],
                                       float_tolerance=float_tolerance, path=sub_path))
    elif isinstance(actual, list):
        assert isinstance(expected, list)
        if len(actual) != len(expected):
            diffs.append(DiffEntry(
                path or "<root>", len(actual), len(expected),
                f"list length mismatch: {len(actual)} vs {len(expected)}",
            ))
            # still diff common prefix
        for i in range(min(len(actual), len(expected))):
            sub_path = f"{path}[{i}]"
            diffs.extend(deep_diff(actual[i], expected[i],
                                   float_tolerance=float_tolerance, path=sub_path))
    elif isinstance(actual, float) or isinstance(expected, float):
        if abs(float(actual) - float(expected)) > float_tolerance:
            diffs.append(DiffEntry(path or "<root>", actual, expected,
                                   f"float differs by {abs(float(actual) - float(expected)):.3e}"))
    else:
        if actual != expected:
            diffs.append(DiffEntry(path or "<root>", actual, expected, "value mismatch"))

    return diffs


def format_diff(diffs: list[DiffEntry], max_value_len: int = 80) -> str:
    if not diffs:
        return "(no diff)"

    def _fmt(v: Any) -> str:
        s = repr(v)
        return s if len(s) <= max_value_len else s[:max_value_len] + "..."

    lines = [f"{len(diffs)} difference(s):"]
    for d in diffs:
        lines.append(f"  {d.path}: {d.reason}")
        lines.append(f"    actual:   {_fmt(d.actual)}")
        lines.append(f"    expected: {_fmt(d.expected)}")
    return "\n".join(lines)
