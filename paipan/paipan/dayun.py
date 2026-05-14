"""
大运 + 流年计算。对应 paipan.js 中 `ec.getYun(...)` 那一段 (paipan.js:167-189)。

直接复用 lunar-python 的 EightChar.getYun() —— 与 Node 侧 lunar-javascript 同作者
(6tail)、同 API。不再在 Python 层实现起运/流年排布逻辑。
"""
from __future__ import annotations

from typing import Literal

from lunar_python import Solar


def compute_dayun(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    gender: Literal["male", "female"],
) -> dict:
    """计算大运 + 流年。

    返回结构与 Node paipan.js 的 result.dayun 逐字段一致：
        - startSolar: str  起运公历日 YYYY-MM-DD
        - startAge: float  起运虚岁 (年 + 月/12 + 日/365)
        - startYearsDesc: str  "{年}年{月}月{天}天后起运"
        - list: List[dict]  8 条大运 (Node slice(1, 9))

    Policy: ``hour == -1`` (unknown-hour sentinel) is coerced to noon, mirroring
    ``compute.py`` upstream. 大运起运仅取决于月柱 + 日/分粒度的节气边界，不依赖
    时辰，所以 noon 占位是安全的——但调用方若绕过 ``compute()`` 直接传 -1，
    需理解此策略。
    """
    # NOTE: paipan.js 外层对 hour=-1 已兜底；此处保持同一策略。
    safe_hour = hour if hour >= 0 else 12
    solar = Solar.fromYmdHms(year, month, day, safe_hour, minute, 0)
    ec = solar.getLunar().getEightChar()

    # NOTE: paipan.js:169 — getYun(sect) 单参数：male=1, female=0
    yun = ec.getYun(1 if gender == "male" else 0)

    start_solar = yun.getStartSolar()
    start_year = yun.getStartYear()
    start_month = yun.getStartMonth()
    start_day = yun.getStartDay()

    # NOTE: paipan.js:173 — 起运虚岁 = 年 + 月/12 + 日/365
    start_age = start_year + start_month / 12.0 + start_day / 365.0

    # NOTE: paipan.js:175 — slice(1, 9) 跳过第 0 条（尚未起运的幼年段），取 8 条
    raw_dayun = yun.getDaYun()
    entries = []
    for dy in raw_dayun[1:9]:
        # NOTE: paipan.js:182 — 每条大运下挂 10 条流年（lunar-javascript LiuNian 按立春切年柱）
        liunian_list = [
            {
                "year": ly.getYear(),
                "ganzhi": ly.getGanZhi(),
                "age": ly.getAge(),
            }
            for ly in dy.getLiuNian()
        ]
        entries.append(
            {
                "index": dy.getIndex(),
                "ganzhi": dy.getGanZhi(),
                "startAge": dy.getStartAge(),
                "startYear": dy.getStartYear(),
                "endYear": dy.getEndYear(),
                "liunian": liunian_list,
            }
        )

    return {
        "startSolar": start_solar.toYmd(),
        "startAge": start_age,
        # NOTE: paipan.js:174 — 模板字符串 "{sy}年{sm}月{sd}天后起运"
        "startYearsDesc": f"{start_year}年{start_month}月{start_day}天后起运",
        "list": entries,
    }
