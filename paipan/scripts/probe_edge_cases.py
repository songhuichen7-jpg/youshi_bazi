"""Edge-case probe for the paipan engine.

Walks through boundary conditions that bug reports usually trace back to:
zi hour (子时) early/late, 节气 crossing, 立春 year boundary, China DST,
hour-unknown placeholder, leap day, far-past / far-future dates, day-pillar
boundary at 23:00 vs 00:00, dayun direction (yang+male / yin+male / etc.)
and true-solar-time city resolution.

Run from repo root:
    uv run --package paipan python paipan/scripts/probe_edge_cases.py

Each probe prints a one-line summary; the script exits 0 always — this is
investigation-mode tooling, not a CI gate. Read stdout for findings.
"""
from __future__ import annotations

from datetime import datetime
from paipan import compute


# 固定 _now，让"今日 GZ"块跨时区跨季节都不变 — 让对比的是排盘逻辑本身
_FIXED_NOW = datetime(2026, 5, 3, 12, 0, 0)


def _summarize(result: dict) -> str:
    sz = result["sizhu"]
    bits = [
        f"年={sz['year']}",
        f"月={sz['month']}",
        f"日={sz['day']}",
        f"时={sz['hour'] or '—'}",
    ]
    if result.get("hourUnknown"):
        bits.append("[时辰未知]")
    if result.get("warnings"):
        bits.append(f"⚠ {len(result['warnings'])}")
    return "  ".join(bits)


def _probe(label: str, **kwargs):
    try:
        r = compute(_now=_FIXED_NOW, **kwargs)
        print(f"  ✓ {label}")
        print(f"      → {_summarize(r)}")
        return r
    except Exception as e:
        print(f"  ✗ {label}")
        print(f"      → EXCEPTION: {type(e).__name__}: {e}")
        return None


def section(title: str):
    print(f"\n━━ {title} ━━")


def zi_hour_boundary():
    section("子时跨日 (early vs late zi)")
    # 同一个时刻 (2026-05-03 23:30)，两套规约。late 把 23 时算到次日子时。
    common = dict(year=2026, month=5, day=3, hour=23, minute=30, gender="male", useTrueSolarTime=False)
    early = _probe("23:30 早子时 (early)", **common, ziConvention="early")
    late = _probe("23:30 晚子时 (late)", **common, ziConvention="late")
    if early and late:
        print(f"      早子时 日柱={early['sizhu']['day']}  时柱={early['sizhu']['hour']}")
        print(f"      晚子时 日柱={late['sizhu']['day']}   时柱={late['sizhu']['hour']}")
        print(f"      late.meta.corrections has late_zi: "
              f"{'late_zi' in [c['type'] for c in late['meta']['corrections']]}")

    # 23:00 整点 — 子时起点
    _probe("23:00 整 早子时", year=2026, month=5, day=3, hour=23, minute=0,
           gender="male", ziConvention="early", useTrueSolarTime=False)
    # 00:00 整 — 子时正中
    _probe("00:00 整", year=2026, month=5, day=4, hour=0, minute=0,
           gender="male", ziConvention="early", useTrueSolarTime=False)
    # 00:59 — 子时末
    _probe("00:59 子时末", year=2026, month=5, day=4, hour=0, minute=59,
           gender="male", ziConvention="early", useTrueSolarTime=False)
    # 01:00 — 丑时起
    _probe("01:00 丑时起", year=2026, month=5, day=4, hour=1, minute=0,
           gender="male", ziConvention="early", useTrueSolarTime=False)


def lichun_year_boundary():
    section("立春前后 (年柱跨年)")
    # 2026 立春: 2026-02-04 04:46 (大约). 立春前应该是 乙巳年，立春后是 丙午年
    _probe("立春前 2026-02-04 04:00", year=2026, month=2, day=4, hour=4, minute=0,
           gender="male", useTrueSolarTime=False)
    _probe("立春后 2026-02-04 05:30", year=2026, month=2, day=4, hour=5, minute=30,
           gender="male", useTrueSolarTime=False)
    # 阳历 1 月底 — 应该还在前一立春年
    _probe("阳历 2026-01-15 12:00", year=2026, month=1, day=15, hour=12, minute=0,
           gender="male", useTrueSolarTime=False)
    # 阳历 12 月底 — 仍在 当前 立春年
    _probe("阳历 2025-12-31 23:00", year=2025, month=12, day=31, hour=23, minute=0,
           gender="male", ziConvention="early", useTrueSolarTime=False)


def jieqi_month_boundary():
    section("节气交接 (月柱跨月)")
    # 2025 立夏: 2025-05-05 14:57 左右. 立夏前是辰月(乙)，立夏后是巳月(丁/壬)
    _probe("立夏前 2025-05-05 12:00", year=2025, month=5, day=5, hour=12, minute=0,
           gender="male", useTrueSolarTime=False)
    _probe("立夏 ~ 2025-05-05 15:00", year=2025, month=5, day=5, hour=15, minute=0,
           gender="male", useTrueSolarTime=False)
    # 2025 惊蛰: 2025-03-05 16:07 — 月柱寅 → 卯
    _probe("惊蛰前 2025-03-05 15:30", year=2025, month=3, day=5, hour=15, minute=30,
           gender="male", useTrueSolarTime=False)
    _probe("惊蛰后 2025-03-05 17:00", year=2025, month=3, day=5, hour=17, minute=0,
           gender="male", useTrueSolarTime=False)


def china_dst():
    section("中国夏令时 1986-1991")
    # 1986-1991 中国 5/4 ~ 9/14 实行 DST (+1h). 输入"DST 期间的钟表时间"
    # 应该被自动减 1h.
    r = _probe("1988-07-15 02:30 (DST 期内)", year=1988, month=7, day=15,
               hour=2, minute=30, gender="male", useTrueSolarTime=False)
    if r:
        types = [c["type"] for c in r["meta"]["corrections"]]
        print(f"      corrections types = {types}")
        if "china_dst" not in types:
            print(f"      ⚠ EXPECTED china_dst correction, did NOT trigger")

    # DST 前夜 / 后夜
    _probe("1988-05-04 01:00 (DST 起前)", year=1988, month=5, day=4,
           hour=1, minute=0, gender="male", useTrueSolarTime=False)
    _probe("1988-09-15 02:00 (DST 末后)", year=1988, month=9, day=15,
           hour=2, minute=0, gender="male", useTrueSolarTime=False)
    # DST 范围外但同年
    _probe("1988-12-15 02:00 (非 DST 季)", year=1988, month=12, day=15,
           hour=2, minute=0, gender="male", useTrueSolarTime=False)
    # DST 没启用之前
    _probe("1985-07-15 02:00 (DST 前)", year=1985, month=7, day=15,
           hour=2, minute=0, gender="male", useTrueSolarTime=False)
    # DST 已停用之后
    _probe("1992-07-15 02:00 (DST 后)", year=1992, month=7, day=15,
           hour=2, minute=0, gender="male", useTrueSolarTime=False)


def hour_unknown():
    section("时辰未知 (-1)")
    r = _probe("hour=-1 时辰未知", year=1993, month=7, day=15, hour=-1,
               gender="male", useTrueSolarTime=False)
    if r:
        sz = r["sizhu"]
        # 时柱必须为 None
        if sz["hour"] is not None:
            print(f"      ⚠ EXPECTED sizhu.hour=None, got {sz['hour']!r}")
        # 时十神 / 藏干 / 纳音 同样为 None
        for k in ("shishen", "cangGan", "naYin"):
            if r[k].get("hour") is not None:
                print(f"      ⚠ EXPECTED {k}.hour=None, got {r[k]['hour']!r}")


def leap_day():
    section("闰年 2 月 29")
    _probe("闰年 2024-02-29 12:00", year=2024, month=2, day=29, hour=12, minute=0,
           gender="female", useTrueSolarTime=False)
    _probe("闰年 2000-02-29 03:00", year=2000, month=2, day=29, hour=3, minute=0,
           gender="male", useTrueSolarTime=False)
    # 非闰年 2/29 (应该被 lunar-python 拒绝 / 抛错)
    _probe("非闰年 2025-02-29 12:00 (期望异常)", year=2025, month=2, day=29,
           hour=12, minute=0, gender="male", useTrueSolarTime=False)


def date_range_extremes():
    section("年份极端值")
    _probe("1900-01-01 00:00", year=1900, month=1, day=1, hour=0, minute=0,
           gender="male", useTrueSolarTime=False)
    _probe("1900-12-31 23:59", year=1900, month=12, day=31, hour=23, minute=59,
           gender="male", useTrueSolarTime=False)
    _probe("2050-06-15 12:00", year=2050, month=6, day=15, hour=12, minute=0,
           gender="female", useTrueSolarTime=False)
    _probe("2099-12-31 23:00", year=2099, month=12, day=31, hour=23, minute=0,
           gender="male", useTrueSolarTime=False)
    _probe("2100-01-01 00:00", year=2100, month=1, day=1, hour=0, minute=0,
           gender="female", useTrueSolarTime=False)


def true_solar_time_cities():
    section("真太阳时 — 城市识别")
    # 北京识别 → 应该有 true_solar_time correction
    r = _probe("北京 1993-07-15 14:30", year=1993, month=7, day=15, hour=14, minute=30,
               city="北京", gender="male", useTrueSolarTime=True)
    if r:
        types = [c["type"] for c in r["meta"]["corrections"]]
        if "true_solar_time" not in types:
            print(f"      ⚠ EXPECTED true_solar_time correction, got types={types}")
        else:
            t = next(c for c in r["meta"]["corrections"] if c["type"] == "true_solar_time")
            print(f"      经度={t['longitude']}  shift={t['shiftMinutes']} min  resolved={t['resolvedCity']!r}")
    # 不存在的城市
    r2 = _probe("瞎编市 1993-07-15 14:30", year=1993, month=7, day=15, hour=14, minute=30,
                city="瞎编市", gender="male", useTrueSolarTime=True)
    if r2:
        if not r2["meta"].get("cityUnknown"):
            print(f"      ⚠ EXPECTED meta.cityUnknown=True for 瞎编市")
        if not any("未识别城市" in w for w in r2["warnings"]):
            print(f"      ⚠ EXPECTED 未识别城市 warning")
    # 西部城市 — shift 应该更大
    _probe("乌鲁木齐 1993-07-15 14:30", year=1993, month=7, day=15, hour=14, minute=30,
           city="乌鲁木齐", gender="male", useTrueSolarTime=True)
    # 关闭真太阳时
    _probe("北京 1993-07-15 14:30 (关闭真太阳时)", year=1993, month=7, day=15,
           hour=14, minute=30, city="北京", gender="male", useTrueSolarTime=False)


def dayun_direction():
    section("大运方向 (阳男阴女顺 / 阴男阳女逆)")
    base = dict(year=2024, month=6, day=15, hour=10, minute=0, useTrueSolarTime=False)
    # 2024 是甲辰年, 甲为阳干
    male_yang = _probe("阳男 2024-06-15 (甲辰阳)", **base, gender="male")
    female_yang = _probe("阳女 2024-06-15 (甲辰阳)", **base, gender="female")
    if male_yang and female_yang:
        # dayun 是 dict，list 在 .list 字段下
        m_list = male_yang["dayun"].get("list") or []
        f_list = female_yang["dayun"].get("list") or []
        m_first = m_list[0] if m_list else None
        f_first = f_list[0] if f_list else None
        print(f"      月柱={male_yang['sizhu']['month']}")
        print(f"      阳男首步 = {m_first['ganzhi'] if m_first else None} @ 起运 {m_first['startAge'] if m_first else None}")
        print(f"      阳女首步 = {f_first['ganzhi'] if f_first else None} @ 起运 {f_first['startAge'] if f_first else None}")
    # 2025 是乙巳年, 乙为阴干
    base25 = dict(year=2025, month=6, day=15, hour=10, minute=0, useTrueSolarTime=False)
    _probe("阴男 2025-06-15 (乙巳阴)", **base25, gender="male")
    _probe("阴女 2025-06-15 (乙巳阴)", **base25, gender="female")


def dst_boundary_critical():
    section("DST 起止边界更严密 (1988 + 1991)")
    # 1988 DST 表: (4, 10, 9, 11). 起在 4/10 02:00.
    _probe("1988-04-10 01:00 (起前 1h)", year=1988, month=4, day=10, hour=1, minute=0,
           gender="male", useTrueSolarTime=False)
    _probe("1988-04-10 02:00 (起点)", year=1988, month=4, day=10, hour=2, minute=0,
           gender="male", useTrueSolarTime=False)
    _probe("1988-04-10 02:30 (起后 30min)", year=1988, month=4, day=10, hour=2, minute=30,
           gender="male", useTrueSolarTime=False)
    _probe("1988-09-11 01:00 (止前 1h)", year=1988, month=9, day=11, hour=1, minute=0,
           gender="male", useTrueSolarTime=False)
    _probe("1988-09-11 02:00 (止点 — DST 末位)", year=1988, month=9, day=11, hour=2, minute=0,
           gender="male", useTrueSolarTime=False)

    # 1991 是最后一个 DST 年: (4, 14, 9, 15)
    _probe("1991-09-14 23:30 (DST 内)", year=1991, month=9, day=14, hour=23, minute=30,
           gender="male", useTrueSolarTime=False)
    _probe("1991-09-15 01:00 (DST 末日早)", year=1991, month=9, day=15, hour=1, minute=0,
           gender="male", useTrueSolarTime=False)
    _probe("1991-09-15 02:00 (止点)", year=1991, month=9, day=15, hour=2, minute=0,
           gender="male", useTrueSolarTime=False)


def jieqi_minute_precision():
    section("节气分钟级精度 (boundary detector)")
    # 2025 立春: 大约 2025-02-03 22:10. 立春前是甲辰，立春后是乙巳.
    _probe("2025 立春前 21:00", year=2025, month=2, day=3, hour=21, minute=0,
           gender="male", useTrueSolarTime=False)
    _probe("2025 立春前 22:00", year=2025, month=2, day=3, hour=22, minute=0,
           gender="male", useTrueSolarTime=False)
    _probe("2025 立春后 22:30", year=2025, month=2, day=3, hour=22, minute=30,
           gender="male", useTrueSolarTime=False)
    _probe("2025 立春后 23:30", year=2025, month=2, day=3, hour=23, minute=30,
           gender="male", useTrueSolarTime=False)
    _probe("2025 立春后 24h+ (2-04 12:00)", year=2025, month=2, day=4, hour=12, minute=0,
           gender="male", useTrueSolarTime=False)


def cross_day_pillar():
    section("日柱在 23:00 / 00:00 边界")
    # 早子时下: 23:00 ~ 00:59 都属当日子时（日柱不变）
    a = _probe("2026-05-03 22:00 早子时前", year=2026, month=5, day=3, hour=22, minute=0,
               gender="male", ziConvention="early", useTrueSolarTime=False)
    b = _probe("2026-05-03 23:30 早子时（同日）", year=2026, month=5, day=3, hour=23, minute=30,
               gender="male", ziConvention="early", useTrueSolarTime=False)
    c = _probe("2026-05-04 00:30 早子时（次日凌晨）", year=2026, month=5, day=4, hour=0, minute=30,
               gender="male", ziConvention="early", useTrueSolarTime=False)
    if a and b and c:
        print(f"      日柱：22:00={a['sizhu']['day']}  23:30={b['sizhu']['day']}  00:30={c['sizhu']['day']}")
        # 在早子派下，22:00 跟 23:30 是同一天，但 00:30 已经是次日（lunar-python 认 00:30 属于"次日子时"）
        if a["sizhu"]["day"] != b["sizhu"]["day"]:
            print(f"      ⚠ 早子派下 22:00 / 23:30 日柱应当相同")


def main():
    print("="*60)
    print(" paipan 边界条件探测  (今日固定 = 2026-05-03)")
    print("="*60)
    zi_hour_boundary()
    lichun_year_boundary()
    jieqi_month_boundary()
    jieqi_minute_precision()
    china_dst()
    dst_boundary_critical()
    hour_unknown()
    leap_day()
    date_range_extremes()
    true_solar_time_cities()
    dayun_direction()
    cross_day_pillar()
    print()


if __name__ == "__main__":
    main()
