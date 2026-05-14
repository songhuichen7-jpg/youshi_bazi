"""
Zi hour convention + jieqi boundary check. Port of
paipan-engine/src/ziHourAndJieqi.js.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from lunar_python import Solar

_HOST_TZ = ZoneInfo("Asia/Shanghai")


def _js_round(x: float) -> int:
    """Match JS Math.round (half-away-from-zero). Python round() uses banker's
    rounding which drifts at .5 boundaries; oracle fixtures固化 against Node."""
    if x >= 0:
        return math.floor(x + 0.5)
    return -math.floor(-x + 0.5)


def _host_utc_timestamp(y: int, mo: int, d: int, h: int, mi: int, s: int = 0) -> float:
    """Convert wall-clock (y, mo, d, h, mi, s) in Asia/Shanghai to UTC seconds.

    Matches Node's ``new Date(y, m-1, d, h, mi, s).getTime()`` on a host in
    Asia/Shanghai — critically, crosses 1986-1991 CDT gap / overlap correctly.
    """
    return datetime(y, mo, d, h, mi, s, tzinfo=_HOST_TZ).astimezone(timezone.utc).timestamp()


def convert_to_late_zi_convention(year: int, month: int, day: int,
                                  hour: int, minute: int) -> dict:
    """
    晚子时派：23:00 起已换日，23:00-01:00 整段都属次日。
    早子时派（默认）：23:00-00:00 属当日。
    只有 hour == 23 时需要加 1 小时（进入次日 00:xx）。

    Returns: {year, month, day, hour, minute, converted}

    ⚠ 语义注意 — late-zi 滚动会顺带影响年柱/月柱
    -------------------------------------
    本函数把 23:xx 整体加 1h 推到次日 00:xx，下游 paipan() 把这个时间一锅
    传给 lunar-python，所以 *年柱、月柱、日柱、时柱* 全都按"次日 00:xx"
    重新算。在大多数情况这跟"日柱归次日，年月按出生原时"的传统读法
    结果一致 —— 因为 23:xx 加 1h 不会跨节气。

    但在 jieqi 落在 23:xx 这种 case，会出现"年/月柱被滚动 1h 跨过节气"：
        eg. 立春 1984-02-04 23:18:44
            出生时间 23:13 (立春前 5 min) + late-zi
            → 滚动到 1984-02-05 00:13 → 越过立春
            → 引擎报 年=甲子 月=丙寅 (新立春年)
            而严格 doctrine 认为：年/月按 23:13 (立春前) → 年=癸亥 月=乙丑

    这是有意保留的 Node port 一致行为（oracle parity）。两种读法在 命理
    圈都有人用，不算 bug —— 但用户可能期望严格读法时会感觉错。
    paipan/tests/regression/birth_inputs.json 的 jieqi-zi-* case 把当前
    行为 pin 住，未来若要改成严格读法需有意为之 + 重生 oracle。

    另一个 lunar-python 自身的怪癖（paipan 不修）：23:00-23:59 段，日柱用
    当日，但时柱按"次日 00:00 子时"用次日的天干起 五鼠遁。所以 戊day
    23:30 给出 day=戊辰 / time=甲子 (取己日的甲子时)，而不是 戊日的壬
    子时。下游用户做 五鼠遁 手算可能对不上 —— 这是 lunar-javascript /
    lunar-python 的设计选择，paipan port 不去改写它。
    """
    # NOTE: ziHourAndJieqi.js:25-27
    if hour != 23:
        return {"year": year, "month": month, "day": day,
                "hour": hour, "minute": minute, "converted": False}
    # NOTE: ziHourAndJieqi.js:28 — Node uses `new Date(...)` with hour+1, which rolls
    # day/month/year automatically. Python datetime + timedelta(hours=1) is equivalent.
    d = datetime(year, month, day, hour, minute, 0) + timedelta(hours=1)
    return {
        "year": d.year,
        "month": d.month,
        "day": d.day,
        "hour": d.hour,
        "minute": d.minute,
        "converted": True,
    }


# 12 个影响月柱的节气（节，非中气）
# NOTE: ziHourAndJieqi.js:40-43
_MONTH_JIE_NAMES = [
    "立春", "惊蛰", "清明", "立夏", "芒种", "小暑",
    "立秋", "白露", "寒露", "立冬", "大雪", "小寒",
]


def check_jieqi_boundary(year: int, month: int, day: int,
                         hour: int, minute: int,
                         threshold_minutes: int = 120) -> dict:
    """
    检查出生时间是否接近节气交界。

    遍历 [year-1, year, year+1] 三年的 jieqi 表，在 12 个"节"中找距离
    输入时间最近的那个。若分钟差 <= threshold_minutes，返回 hint。

    Returns: {isNearBoundary, jieqi, jieqiTime, minutesDiff, hint}

    Note: jieqiTime is a raw lunar_python.Solar (mirror of Node closest.solar);
    callers unwrap via .getYear() / .getMonth() / .getDay() / .getHour() / .getMinute().
    """
    # NOTE: ziHourAndJieqi.js:56 — birth timestamp for comparison.
    # Node 用 `new Date(y, m-1, d, h, mi, 0).getTime()` 取 UTC ms，宿主 Asia/Shanghai
    # 时会跨过 1986-1991 CDT gap — 用 aware UTC timestamp 复现。
    birth_ts = _host_utc_timestamp(year, month, day, hour, minute, 0)

    closest_name: str | None = None
    closest_solar = None
    closest_diff_seconds: float | None = None

    # NOTE: ziHourAndJieqi.js:59 — iterate 3 years to handle jieqi straddling year boundary
    for target_year in (year - 1, year, year + 1):
        # NOTE: ziHourAndJieqi.js:60 — Solar.fromYmdHms(year, 6, 1, 0, 0, 0) → lunar → jieqi table
        lunar = Solar.fromYmdHms(target_year, 6, 1, 0, 0, 0).getLunar()
        table = lunar.getJieQiTable()
        for name in _MONTH_JIE_NAMES:
            s = table.get(name)
            if s is None:
                continue
            jq_ts = _host_utc_timestamp(
                s.getYear(), s.getMonth(), s.getDay(),
                s.getHour(), s.getMinute(), s.getSecond(),
            )
            diff_seconds = abs(jq_ts - birth_ts)
            if closest_diff_seconds is None or diff_seconds < closest_diff_seconds:
                closest_name = name
                closest_solar = s
                closest_diff_seconds = diff_seconds

    # NOTE: ziHourAndJieqi.js:76 — Math.round(diff / 60000) → round to integer minutes.
    # Use JS-compatible rounding to avoid banker's-rounding drift on .5 boundaries.
    minutes_diff = _js_round(closest_diff_seconds / 60.0) if closest_diff_seconds is not None else None
    is_near_boundary = (minutes_diff is not None
                        and minutes_diff <= threshold_minutes)

    hint: str | None = None
    if is_near_boundary and closest_solar is not None:
        s = closest_solar
        # NOTE: ziHourAndJieqi.js:82 — zero-pad month/day/hour/minute to 2 digits
        time_str = (f"{s.getYear()}-{s.getMonth():02d}-{s.getDay():02d} "
                    f"{s.getHour():02d}:{s.getMinute():02d}")
        # NOTE: ziHourAndJieqi.js:83 — exact user-facing wording, do not alter
        hint = (f"你的出生时间距离「{closest_name}」（{time_str}）仅 "
                f"{minutes_diff} 分钟，年柱或月柱在此节气前后不同，"
                f"请仔细核对出生时间是否精确。")

    return {
        "isNearBoundary": is_near_boundary,
        "jieqi": closest_name,
        "jieqiTime": closest_solar,
        "minutesDiff": minutes_diff,
        "hint": hint,
    }
