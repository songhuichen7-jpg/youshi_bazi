"""Deep probe: 节气在 23:00-01:00 这种"前夜/凌晨"边界附近.

为什么重要：
  这里是排盘里 *最容易出错* 的复合边界 — 同一段几分钟里同时发生：
    1. 月柱可能跨节气（甲→乙月）
    2. 日柱可能跨日（早/晚子时不同）
    3. 早子派下 23-24 时归当日，晚子派下 23 时已归次日
    4. 立春跨节气还会同步切年柱
  四个轴叠到一起，bug 滋生概率 N². 走完这一段，绝大部分排盘正确性怀疑
  就能落地。

策略：
  Stage 1 — 扫 1980-2030 共 50 年的 12 个"节"（影响月柱），找出落在 23:00-01:00
            窗口内的 jieqi 时刻。
  Stage 2 — 对每个找到的 case，分别测：
              · 节气前 5 分钟 + 早子派
              · 节气前 5 分钟 + 晚子派
              · 节气当时整 + 早子派
              · 节气当时整 + 晚子派
              · 节气后 5 分钟 + 早子派
              · 节气后 5 分钟 + 晚子派
            观察月柱 / 日柱 / 年柱（如果 jieqi 是立春）的变化是否符合预期，
            并且 corrections 字段（late_zi）是否落账。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from lunar_python import Solar
from paipan import compute


_FIXED_NOW = datetime(2026, 5, 3, 12, 0, 0)

# 12 个"节"（影响月柱的，不含中气）
_JIEQI_NAMES = [
    "立春", "惊蛰", "清明", "立夏", "芒种", "小暑",
    "立秋", "白露", "寒露", "立冬", "大雪", "小寒",
]


def find_jieqi_near_zi_hour(start_year: int, end_year: int) -> list[dict]:
    """扫这段年份范围所有 jieqi，挑出 23:00-23:59 或 00:00-00:59 的."""
    cases: list[dict] = []
    for y in range(start_year, end_year + 1):
        lunar = Solar.fromYmdHms(y, 6, 1, 0, 0, 0).getLunar()
        table = lunar.getJieQiTable()
        for name in _JIEQI_NAMES:
            s = table.get(name)
            if s is None:
                continue
            h = s.getHour()
            if h == 23 or h == 0:
                cases.append({
                    "name": name,
                    "year": s.getYear(),
                    "month": s.getMonth(),
                    "day": s.getDay(),
                    "hour": s.getHour(),
                    "minute": s.getMinute(),
                    "second": s.getSecond(),
                })
    return cases


def _bazi_str(r):
    sz = r["sizhu"]
    return (
        f"年={sz['year']:>4}  月={sz['month']:>4}  日={sz['day']:>4}  "
        f"时={sz['hour'] or '—':>4}"
    )


def probe_around(case: dict):
    """对单个 jieqi case 做 6 个角度的探针."""
    name = case["name"]
    print(f"\n━━ {name} {case['year']:04d}-{case['month']:02d}-{case['day']:02d} "
          f"{case['hour']:02d}:{case['minute']:02d} ━━")

    base_dt = datetime(case["year"], case["month"], case["day"],
                       case["hour"], case["minute"])

    offsets = [
        ("节气前 5 min", base_dt - timedelta(minutes=5)),
        ("节气当时   ", base_dt),
        ("节气后 5 min", base_dt + timedelta(minutes=5)),
    ]
    for off_label, dt in offsets:
        for zi_label, zi_conv in [("早子派", "early"), ("晚子派", "late")]:
            try:
                r = compute(
                    year=dt.year, month=dt.month, day=dt.day,
                    hour=dt.hour, minute=dt.minute,
                    gender="male",
                    ziConvention=zi_conv,
                    useTrueSolarTime=False,
                    _now=_FIXED_NOW,
                )
                # corrections 里有 late_zi 时标个 *
                has_late = any(c["type"] == "late_zi" for c in r["meta"]["corrections"])
                star = "*" if has_late else " "
                print(f"  {off_label}  [{zi_label}]  {dt.strftime('%Y-%m-%d %H:%M')}{star}  →  {_bazi_str(r)}")
            except Exception as e:
                print(f"  {off_label}  [{zi_label}]  {dt.strftime('%Y-%m-%d %H:%M')}   →  EXC: {e}")


def main():
    print("="*80)
    print(" Stage 1 — 扫 1980-2030 找 jieqi 落在 23:xx / 00:xx 的 case")
    print("="*80)
    cases = find_jieqi_near_zi_hour(1980, 2030)
    print(f"\n找到 {len(cases)} 个 jieqi 在 zi-hour 窗口内：")
    for c in cases:
        print(f"  · {c['name']:>4}  {c['year']:04d}-{c['month']:02d}-{c['day']:02d} "
              f"{c['hour']:02d}:{c['minute']:02d}:{c['second']:02d}")

    print()
    print("="*80)
    print(" Stage 2 — 对每个 case 做 6 角度探针  (* = late_zi correction 已落账)")
    print("="*80)
    # 挑代表性的几个 — 全跑会刷屏
    # 立春 (跨年柱) 优先；其他 jieqi 各取 1-2 个
    grouped: dict[str, list[dict]] = {}
    for c in cases:
        grouped.setdefault(c["name"], []).append(c)
    representative: list[dict] = []
    if "立春" in grouped:
        representative.extend(grouped["立春"][:2])
    for name in _JIEQI_NAMES:
        if name == "立春":
            continue
        if name in grouped:
            representative.append(grouped[name][0])

    print(f"\n挑了 {len(representative)} 个代表 case 做深探：")
    for c in representative:
        probe_around(c)

    print()
    print("="*80)
    print(" Stage 3 — 关键观察")
    print("="*80)
    print("""
  · 月柱 应在 jieqi 前后切换（不论早/晚子派）— 节气是绝对时间点，跟子时
    规约无关
  · 日柱 在 23:00-23:59 段：早子派 = 当日；晚子派 = 次日 (有 late_zi 标 *)
  · 日柱 在 00:00-00:59 段：两派都已经是次日 (无需 late_zi 调整)
  · 时柱 在 23-01 整段都应该是子时（壬子/癸子等），跟规约无关
  · 立春 在 23:xx/00:xx 时：年柱也跟着切，跟月柱同步
""")


if __name__ == "__main__":
    main()
