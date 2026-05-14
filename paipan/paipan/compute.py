"""
Paipan main entry. Port of paipan-engine/src/paipan.js.

Processing pipeline (mirrors Node paipan() exactly):
  1. DST correction (if hour known)
  2. True solar time (if hour known, useTrueSolarTime, longitude available)
  3. Zi hour convention (if late)
  4. Jieqi boundary warning (stored in meta.jieqiCheck when hour known)
  5. lunar-python Solar → EightChar → 四柱/十神/藏干/纳音
  6. Today's GZ (injectable via _now for deterministic tests)
  7. Dayun + liunian (via compute_dayun; only needs month pillar + gender)
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from lunar_python import Solar

from paipan.analyzer import analyze
from paipan.china_dst import correct_china_dst
from paipan.cities import get_city_coords
from paipan.dayun import compute_dayun
from paipan.solar_time import to_true_solar_time
from paipan.xingyun import build_xingyun
from paipan.zi_hour import check_jieqi_boundary, convert_to_late_zi_convention


def _serialize_jieqi_solar(s) -> dict:
    """Mirror lunar-javascript Solar JSON.stringify shape.

    Node's JSON.stringify(solar) emits {"_p": {year, month, day, hour, minute, second}}
    because lunar-javascript stores those on an internal `_p` object. We replicate
    that exact shape so the regression oracle matches byte-for-byte.
    """
    return {
        "_p": {
            "year": s.getYear(),
            "month": s.getMonth(),
            "day": s.getDay(),
            "hour": s.getHour(),
            "minute": s.getMinute(),
            "second": s.getSecond(),
        }
    }


def compute(
    *,
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int = 0,
    city: Optional[str] = None,
    longitude: Optional[float] = None,
    gender: Literal["male", "female"],
    ziConvention: Literal["early", "late"] = "early",
    useTrueSolarTime: bool = True,
    _now: Optional[datetime] = None,
) -> dict:
    """Top-level paipan entry.

    Args match Node paipan() opts 1:1. `_now` is a test-only injection point for
    the "today's GZ" phase; defaults to datetime.now().

    Returns: dict with keys sizhu, rizhu, shishen, cangGan, naYin, dayun, lunar,
    solarCorrected, warnings, meta, hourUnknown, todayYearGz, todayMonthGz,
    todayDayGz, todayYmd — matching Node output field-for-field.
    """
    warnings: list[str] = []
    # NOTE: paipan.js:46-49 — meta.input 照抄输入（包含 hour=-1 原值），corrections 初始为 []
    meta: dict = {
        "input": {"year": year, "month": month, "day": day, "hour": hour, "minute": minute},
        "corrections": [],
    }

    # NOTE: paipan.js:52-55 — 未知时辰：hour==-1 → 占位 12:00，用于 lunar/dayun 计算
    hourUnknown = hour == -1
    h = 12 if hourUnknown else hour
    mi = minute or 0
    y, mo, d = year, month, day

    # NOTE: paipan.js:58-69 — Step 1: DST 修正
    if not hourUnknown:
        dst = correct_china_dst(y, mo, d, h, mi)
        if dst["wasDst"]:
            meta["corrections"].append({
                "type": "china_dst",
                "from": f"{y}-{mo}-{d} {h}:{mi}",
                "to": f"{dst['year']}-{dst['month']}-{dst['day']} {dst['hour']}:{dst['minute']}",
            })
            y, mo, d, h, mi = dst["year"], dst["month"], dst["day"], dst["hour"], dst["minute"]
            # NOTE: paipan.js:67 — 中文警告字符级别逐字照抄
            warnings.append(
                "1986-1991 中国实行过夏令时，已自动减 1 小时。若你不确定当时是否用夏令时，请核对。"
            )

    # NOTE: paipan.js:72-96 — Step 2: 真太阳时
    lng = longitude
    resolvedCity: Optional[str] = None
    if lng is None and city:
        c = get_city_coords(city)
        if c is not None:
            lng = c.lng
            resolvedCity = c.canonical
    if useTrueSolarTime and not hourUnknown and city and lng is None:
        # NOTE: paipan.js:80 — 未识别城市警告，字符级别照抄
        warnings.append(
            f"未识别城市\"{city}\"，未做真太阳时修正。可以换个常见行政名（例如\"北京\"、\"长沙\"、\"苏州\"），或在高级选项里关闭\"修正真太阳时\"。"
        )
        meta["cityUnknown"] = True
    if useTrueSolarTime and not hourUnknown and lng is not None:
        t = to_true_solar_time(y, mo, d, h, mi, lng)
        meta["corrections"].append({
            "type": "true_solar_time",
            "longitude": lng,
            "longitudeMinutes": t["longitudeMinutes"],
            "eotMinutes": t["eotMinutes"],
            "shiftMinutes": t["shiftMinutes"],
            "resolvedCity": resolvedCity,
            "from": f"{y}-{mo}-{d} {h}:{mi}",
            "to": f"{t['year']}-{t['month']}-{t['day']} {t['hour']}:{t['minute']}",
        })
        y, mo, d, h, mi = t["year"], t["month"], t["day"], t["hour"], t["minute"]

    # NOTE: paipan.js:99-109 — Step 3: 晚子时派转换
    if not hourUnknown and ziConvention == "late":
        z = convert_to_late_zi_convention(y, mo, d, h, mi)
        if z["converted"]:
            meta["corrections"].append({
                "type": "late_zi",
                "from": f"{y}-{mo}-{d} {h}:{mi}",
                "to": f"{z['year']}-{z['month']}-{z['day']} {z['hour']}:{z['minute']}",
            })
            y, mo, d, h, mi = z["year"], z["month"], z["day"], z["hour"], z["minute"]

    # NOTE: paipan.js:112-116 — Step 4: 节气交界检查（hourUnknown 时跳过，不写 meta.jieqiCheck）
    if not hourUnknown:
        jq = check_jieqi_boundary(y, mo, d, h, mi)
        if jq["isNearBoundary"]:
            warnings.append(jq["hint"])
        # 把原始 Solar 换成 Node JSON.stringify 等价的 {_p: {...}}，匹配 oracle 字节。
        meta["jieqiCheck"] = {
            "isNearBoundary": jq["isNearBoundary"],
            "jieqi": jq["jieqi"],
            "jieqiTime": _serialize_jieqi_solar(jq["jieqiTime"]) if jq["jieqiTime"] is not None else None,
            "minutesDiff": jq["minutesDiff"],
            "hint": jq["hint"],
        }

    # NOTE: paipan.js:119-121 — Step 5: lunar-python 排盘
    solar = Solar.fromYmdHms(y, mo, d, h, mi, 0)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()

    # NOTE: paipan.js:123-154 — 组装返回字段；字段顺序与 Node 对齐
    result: dict = {
        "sizhu": {
            "year": ec.getYear(),
            "month": ec.getMonth(),
            "day": ec.getDay(),
            "hour": None if hourUnknown else ec.getTime(),
        },
        "rizhu": ec.getDayGan(),
        "shishen": {
            "year": ec.getYearShiShenGan(),
            "month": ec.getMonthShiShenGan(),
            "hour": None if hourUnknown else ec.getTimeShiShenGan(),
        },
        "cangGan": {
            "year": ec.getYearHideGan(),
            "month": ec.getMonthHideGan(),
            "day": ec.getDayHideGan(),
            "hour": None if hourUnknown else ec.getTimeHideGan(),
        },
        "naYin": {
            "year": ec.getYearNaYin(),
            "month": ec.getMonthNaYin(),
            "day": ec.getDayNaYin(),
            "hour": None if hourUnknown else ec.getTimeNaYin(),
        },
        "dayun": [],
        "lunar": str(lunar),
        # NOTE: paipan.js:150 — solarCorrected 零填充到 2 位
        "solarCorrected": f"{y}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}",
        "warnings": warnings,
        "meta": meta,
        "hourUnknown": hourUnknown,
    }

    # NOTE: paipan.js:157-165 — 今天所属的"立春年"年柱（用于 UI 高亮 current 大运/流年）
    now = _now if _now is not None else datetime.now()
    today_solar = Solar.fromYmdHms(now.year, now.month, now.day, 12, 0, 0)
    today_ec = today_solar.getLunar().getEightChar()
    result["todayYearGz"] = today_ec.getYear()
    result["todayMonthGz"] = today_ec.getMonth()
    result["todayDayGz"] = today_ec.getDay()
    result["todayYmd"] = f"{now.year}-{now.month:02d}-{now.day:02d}"

    # NOTE: paipan.js:168-189 — 大运：委托给 compute_dayun（仅依赖月柱 + 性别）
    # compute_dayun 内部对 hour==-1 做 noon 兜底，这里直接把原 hour 传下去即可。
    result["dayun"] = compute_dayun(y, mo, d, h, mi, gender)

    analysis = analyze(result)
    result["force"] = analysis["force"]
    result["geJu"] = analysis["geJu"]
    result["ganHe"] = analysis["ganHe"]
    result["zhiRelations"] = analysis["zhiRelations"]
    result["notes"] = analysis["notes"]
    result["dayStrength"] = analysis["force"]["dayStrength"]
    main_candidate = analysis["geJu"].get("mainCandidate") or {}
    result["geju"] = main_candidate.get("name") or ""
    # Plan 7.3: yongshen is now a structured engine. Top-level key stays a STRING
    # (chartUi.js compat); full dict goes in yongshenDetail.
    result["yongshen"] = analysis["yongshen"]
    result["yongshenDetail"] = analysis["yongshenDetail"]
    # Plan 7.4: 行运 evaluation against 命局 用神 (Plan 7.3 anchor)
    bazi = result["sizhu"]
    mingju_gans = [bazi[k][0] for k in ['year', 'month', 'day', 'hour'] if bazi.get(k)]
    mingju_zhis = [bazi[k][1] for k in ['year', 'month', 'day', 'hour'] if bazi.get(k)]
    chart_context = None
    month_str = bazi.get("month")
    day_str = bazi.get("day")
    if month_str and day_str:
        chart_context = {
            'month_zhi': month_str[1],
            'rizhu_gan': day_str[0],
            'force': analysis.get("force") or {},
            'gan_he': analysis.get("ganHe") or {},
            'original_geju_name': (
                (analysis.get("geJu") or {}).get("mainCandidate", {}).get("name", '') or ''
            ),
        }
    result["xingyun"] = build_xingyun(
        dayun=result["dayun"],
        yongshen_detail=result["yongshenDetail"],
        mingju_gans=mingju_gans,
        mingju_zhis=mingju_zhis,
        current_year=now.year,
        chart_context=chart_context,
    )

    return result
