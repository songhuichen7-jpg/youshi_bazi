# paipan-engine Node.js 源文件盘点

> **用途：** Python port（Tasks 9-20）的"真值参考"。每个 Task 的实现者读本文 + 对应 .js 文件即可，不必重复阅读其他文件。
>
> **生成日期：** 2026-04-17
> **方法：** 逐字阅读所有 12 个 .js 文件，以实际代码为准，不采纳任何推断。

---

## 文件列表

```
paipan-engine/src/
├── paipan.js              # 主入口，排盘封装
├── solarTime.js           # 真太阳时修正
├── chinaDst.js            # 中国1986-1991夏令时修正
├── ziHourAndJieqi.js      # 子时归属 + 节气交界检查
├── cities.js              # 城市→经纬度查询
└── ming/
    ├── ganzhi.js          # 天干地支基础常量 + 五行生克
    ├── shishen.js         # 十神计算
    ├── cangGan.js         # 地支藏干表
    ├── liLiang.js         # 力量擂台（十神得分）
    ├── geJu.js            # 格局识别
    ├── heKe.js            # 天干合、地支冲/合/三合
    └── analyze.js         # 命理层主入口（调用 server.js）
```

总计：12 个 .js 文件（含 1 个辅助数据文件 `cities-data.json`，不翻译）。

---

## 各文件详情

---

### `paipan.js` — 排盘主封装层

**导出：** `{ paipan }`

**签名：**
```js
paipan(opts) → Object
```

**参数（opts 对象字段）：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `year` | number | 是 | 公历年 |
| `month` | number | 是 | 1-12 |
| `day` | number | 是 | 日 |
| `hour` | number | 是 | 0-23，未知传 -1 |
| `minute` | number | 是 | 0-59 |
| `city` | string | 条件 | 城市名，用于真太阳时修正 |
| `longitude` | number | 条件 | 直接提供经度（优先于 city）|
| `gender` | `'male'|'female'` | 是 | 性别（影响大运顺逆） |
| `ziConvention` | `'early'|'late'` | 否，默认 `'early'` | 子时派 |
| `useTrueSolarTime` | boolean | 否，默认 `true` | 是否修正真太阳时 |

**返回对象结构：**
```js
{
  sizhu: {
    year: string,   // 年柱干支，如 "甲子"
    month: string,  // 月柱
    day: string,    // 日柱
    hour: string|null,  // 时柱，hour=-1 时为 null
  },
  rizhu: string,          // 日主天干，如 "甲"
  shishen: {
    year: string,   // 年干十神（ec.getYearShiShenGan()）
    month: string,
    hour: string|null,
    // 注：日主本位不在此，直接用 rizhu
  },
  cangGan: {
    year: string,   // 年支藏干字符串（ec.getYearHideGan()，lunar-javascript 格式）
    month: string,
    day: string,
    hour: string|null,
  },
  naYin: {
    year: string,   // 年柱纳音（ec.getYearNaYin()）
    month: string,
    day: string,
    hour: string|null,
  },
  dayun: {
    startSolar: string,     // 起运公历日期 "YYYY-MM-DD"
    startAge: number,       // 起运年龄（小数，含月/日分量）
    startYearsDesc: string, // 描述，如 "3年2月5天后起运"
    list: Array<{           // 8 个大运（slice(1,9)，跳过索引 0）
      index: number,
      ganzhi: string,
      startAge: number,
      startYear: number,
      endYear: number,
      liunian: Array<{      // 每大运内 10 个流年
        year: number,
        ganzhi: string,
        age: number,
      }>,
    }>,
  },
  lunar: string,            // 农历描述字符串
  solarCorrected: string,   // 修正后公历时间 "YYYY-MM-DD HH:mm"
  warnings: string[],       // 用户可读警告
  meta: {
    input: { year, month, day, hour, minute },
    corrections: Array<{type, from, to, ...}>,
    jieqiCheck: Object,     // checkJieqiBoundary 返回值
    cityUnknown?: boolean,
  },
  hourUnknown: boolean,
  todayYearGz: string,      // 今天所在"立春年"年柱（UI 高亮用）
  todayMonthGz: string,
  todayDayGz: string,
  todayYmd: string,
}
```

**处理顺序：**
1. hour === -1 → 标记 hourUnknown，占位 h = 12（不做 DST/真太阳时/子时处理）
2. DST 修正（仅非未知时辰）→ `correctChinaDst()` `# NOTE: paipan.js:58` — `if (!hourUnknown)` 明确跳过
3. 真太阳时修正（仅非未知时辰 + longitude 可解析）→ `toTrueSolarTime()` `# NOTE: paipan.js:83`
4. 晚子时转换（仅非未知时辰 + ziConvention === 'late'）→ `convertToLateZiConvention()` `# NOTE: paipan.js:99`
5. 节气交界检查（仅非未知时辰）→ `checkJieqiBoundary()` `# NOTE: paipan.js:112`
6. `Solar.fromYmdHms()` → `getLunar()` → `getEightChar()` 算四柱

**外部依赖：** `lunar-javascript`（`Solar`），本项目的 `solarTime`, `chinaDst`, `ziHourAndJieqi`, `cities`

**注意事项：**
- `ziConvention` 参数**存在且使用**（计划草稿说"不确定"——实际已完整实现）
- 城市不识别时**有明确 warning**，不静默跳过
- 大运 `list` 用 `.slice(1, 9)` 跳过第 0 个大运（命理惯例，0 = 胎元/命宫前大运）
- 今日干支（`todayYearGz` 等）用当日正午 12 点计算，避免子时边界歧义
- `gender` 映射：`'male'` → 1，`'female'` → 0，传入 `getYun()`

---

### `solarTime.js` — 真太阳时修正

**导出：** `{ toTrueSolarTime, equationOfTime }`

**签名：**
```js
equationOfTime(date: Date) → number   // 均时差（分钟，正=真太阳快于平太阳）
toTrueSolarTime(year, month, day, hour, minute, longitude) → Object
```

**toTrueSolarTime 返回：**
```js
{
  year, month, day, hour, minute,
  shiftMinutes: number,      // 总修正量（四舍五入到 0.1 分钟）
  eotMinutes: number,        // 均时差分量
  longitudeMinutes: number,  // 经度时差分量
}
```

**算法：**
1. 经度时差：`(longitude - 120) × 4` 分钟（120°E 为北京时基准）
2. 均时差（EoT）：Meeus《天文算法》简化式，精度 ±1 分钟
   - `N` = 年内第几天（从 Jan 1 起）
   - `B = 2π(N-81)/365`
   - `EoT = 9.87·sin(2B) - 7.53·cos(B) - 1.5·sin(B)`（分钟）
   - `# NOTE: solarTime.js:30-32` — 三个系数（9.87 / 7.53 / 1.5）是 Meeus 公式的 simplified form；port 必须按**同样常量、同样运算顺序**计算，否则 EoT 会有浮点偏差，oracle 对不上。
3. 总修正 = 经度时差 + EoT，加到北京时间上

**实现细节（`# NOTE: solarTime.js:21`）：**
- N 的计算：`Date.UTC(year, 0, 0)` 作为基点，用毫秒差 / 86400000 得整数天
- EoT 用**北京时的 UTC 等效时间戳**计算（`hour - 8`），时间层面正确

**外部依赖：** 无（纯数学）

---

### `chinaDst.js` — 中国夏令时修正

**导出：** `{ isChinaDst, correctChinaDst, CHINA_DST_PERIODS }`

**签名：**
```js
isChinaDst(year, month, day, hour) → boolean
correctChinaDst(year, month, day, hour, minute) → { year, month, day, hour, minute, wasDst }
```

**数据（`CHINA_DST_PERIODS`）：** `# NOTE: chinaDst.js:16-24` — 6 年 DST 起止日期是硬编码的数据源，port 必须逐字节一致。
```js
// 年份, 开始[月,日], 结束[月,日]
{ year: 1986, start: [5, 4],  end: [9, 14] }
{ year: 1987, start: [4, 12], end: [9, 13] }
{ year: 1988, start: [4, 10], end: [9, 11] }
{ year: 1989, start: [4, 16], end: [9, 17] }
{ year: 1990, start: [4, 15], end: [9, 16] }
{ year: 1991, start: [4, 14], end: [9, 15] }
```

**逻辑：** DST 区间 = `[start日 02:00, end日 02:00)`（半开区间）。在区间内则减 1 小时还原真实时间。

**注意事项：**
- `isChinaDst` 只接受 `hour`，不接受 `minute`（分钟粒度的边界极少见，忽略）
- 1985 及之前、1992 及之后返回 false

---

### `ziHourAndJieqi.js` — 子时归属 + 节气交界提示

**导出：** `{ convertToLateZiConvention, checkJieqiBoundary }`

**签名：**
```js
convertToLateZiConvention(year, month, day, hour, minute)
  → { year, month, day, hour, minute, converted: boolean }

checkJieqiBoundary(year, month, day, hour, minute, thresholdMinutes = 120)
  → { isNearBoundary, jieqi, jieqiTime, minutesDiff, hint }
```

**convertToLateZiConvention：**
- 只在 `hour === 23` 时触发（`converted: true`），加 1 小时进入次日 00:xx
- 其他小时直接透传，`converted: false`

**checkJieqiBoundary：**
- 检测 12 个"月节"（非中气）：立春、惊蛰、清明、立夏、芒种、小暑、立秋、白露、寒露、立冬、大雪、小寒
- 搜索范围：`year-1`, `year`, `year+1` 三年的节气表，找最近的"节"
- 距离 ≤ `thresholdMinutes` 分钟（默认 120）时，`isNearBoundary = true`，附带 `hint` 文字
- `jieqiTime` 是 lunar-javascript 的 `Solar` 对象（非普通 Date）

**外部依赖：** `lunar-javascript`（`Solar`）

**注意事项（`# NOTE: ziHourAndJieqi.js:52`）：**
- `Solar.fromYmdHms(year, month - 1 + 1, ...)` 写法等效 `month`，无 off-by-one

---

### `cities.js` — 城市经纬度查询

**导出：** `{ CITIES, getCityCoords, listCityNames, normalize }`

**签名：**
```js
getCityCoords(raw: string) → { lng, lat, canonical } | null
listCityNames(limit?: number) → string[]
normalize(raw: string) → string   // 剥后缀规范化
```

**数据来源：**
- 主数据：`cities-data.json`（pyecharts MIT，~3750 条，格式 `{ 城市名: [lng, lat] }`）
- 补充：`OVERSEAS` 常量（22 个海外城市，格式相同，覆盖到 RAW）

**查询策略（三级回退）：**
1. 精确匹配（原字符串）
2. 规范化匹配（剥后缀，两次，如"湖南省"→"湖南"）
3. 子串模糊匹配（"湖南长沙"→"长沙"；"浦东"→"浦东新区"）

**后缀剥离顺序（`SUFFIXES` 数组，长→短）：**
- 优先剥完整自治区名（维吾尔自治区、壮族自治区等），再剥短后缀（省/市/区/县…）

**CITIES 导出：**
- 等于 `RAW`（含 OVERSEAS 合并后），供旧代码用 `Object.keys(CITIES)` 枚举

**外部依赖：** Node.js `fs`, `path`（读取 JSON 文件）

**注意事项：**
- 模块加载时一次性构建两个 Map（`EXACT_MAP` / `NORM_MAP`），不在查询时重建
- 冲突时偏向原名带 `市/县/区/旗/州/盟` 的条目（更精确的行政名）

---

### `ming/ganzhi.js` — 天干地支基础常量

**导出：**
```js
TIAN_GAN, DI_ZHI,
GAN_WUXING, GAN_YINYANG,
ZHI_WUXING, ZHI_YINYANG,
WUXING_SHENG, WUXING_KE,
generates, overcomes,
DIZHI_MONTH, ZHI_CATEGORY,
```

**内容：**
- `TIAN_GAN`：10 天干数组 `['甲','乙',...,'癸']`
- `DI_ZHI`：12 地支数组 `['子','丑',...,'亥']`
- `GAN_WUXING`：天干→五行（木/火/土/金/水）
- `GAN_YINYANG`：天干→阴阳（阳=甲丙戊庚壬，阴=乙丁己辛癸）
- `ZHI_WUXING`：地支→五行（本气，四库=土）
- `ZHI_YINYANG`：地支→阴阳（子寅辰午申戌=阳，丑卯巳未酉亥=阴）
- `WUXING_SHENG`：五行相生 `{ 木:'火', 火:'土', 土:'金', 金:'水', 水:'木' }`
- `WUXING_KE`：五行相克 `{ 木:'土', 土:'水', 水:'火', 火:'金', 金:'木' }`
- `generates(a, b) → boolean`：a 生 b
- `overcomes(a, b) → boolean`：a 克 b
- `DIZHI_MONTH`：地支→月序（寅=1, 卯=2 … 丑=12，按节气月令）
- `ZHI_CATEGORY`：地支→分类（四仲/四孟/四库）

**外部依赖：** 无

---

### `ming/shishen.js` — 十神计算

**导出：** `{ getShiShen, getShiShenGroup, SHI_SHEN_PAIRS }`

**签名：**
```js
getShiShen(riZhu: string, gan: string) → string
getShiShenGroup(shishen: string) → string | null
```

**注意：计划草稿中的签名顺序错误。**
- 草稿写 `getShiShen(dayGan, otherGan)` 参数名虽相近，但参数**第一个是日主**，第二个是目标天干，正确。
- 函数内部用 `riZhu` 指第一参数，`gan` 指第二参数，不存在歧义。

**计算规则（以日主五行+阴阳为基准）：**
| 关系 | 同阴阳 | 异阴阳 |
|------|--------|--------|
| 同五行 | 比肩 | 劫财 |
| 日主生 | 食神 | 伤官 |
| 日主克 | 偏财 | 正财 |
| 克日主 | 七杀 | 正官 |
| 生日主 | 偏印 | 正印 |

**SHI_SHEN_PAIRS：**
```js
{
  比劫: ['比肩', '劫财'],
  食伤: ['食神', '伤官'],
  财:   ['正财', '偏财'],
  官杀: ['正官', '七杀'],
  印:   ['正印', '偏印'],
}
```

**外部依赖：** `./ganzhi`（`GAN_WUXING`, `GAN_YINYANG`, `WUXING_SHENG`, `WUXING_KE`）

---

### `ming/cangGan.js` — 地支藏干表

**导出：** `{ CANG_GAN, getBenQi, getCangGan }`

**签名：**
```js
getCangGan(zhi: string) → Array<{ gan, weight, role }>
getBenQi(zhi: string) → string   // 本气天干
```

**注意：计划草稿签名 `getCangGan(zhi)` 正确，但未说明返回带权重。**

**权重体系：**
- 本气：weight = 1.0
- 中气：weight = 0.5
- 余气：weight = 0.3

**各地支藏干（完整表）：**

| 地支 | 本气 | 中气 | 余气 |
|------|------|------|------|
| 子 | 癸 | — | — |
| 丑 | 己 | 癸 | 辛 |
| 寅 | 甲 | 丙 | 戊 |
| 卯 | 乙 | — | — |
| 辰 | 戊 | 乙 | 癸 |
| 巳 | 丙 | 戊 | 庚 |
| 午 | 丁 | 己 | — |
| 未 | 己 | 丁 | 乙 |
| 申 | 庚 | 壬 | 戊 |
| 酉 | 辛 | — | — |
| 戌 | 戊 | 辛 | 丁 |
| 亥 | 壬 | 甲 | — |

**外部依赖：** 无

---

### `ming/liLiang.js` — 力量擂台

> ⚠️ **PORT DIRECTIVE — keDiscount**: The source defines `keDiscount: 0.6` at liLiang.js:30 but **NEVER applies it** in any calculation. Only `heDiscount` is used (lines 101-117 block).
>
> The Python port MUST replicate this exactly — define the constant in the weights dict, do NOT implement the "被克减分" logic. Oracle regression will fail if you "fix" this in Python.
>
> If the ke-reduction is truly wanted, that is a separate algorithm-correction project: update Node liLiang.js first, regenerate all oracle fixtures, THEN update Python in lockstep. See `paipan/tests/regression/generate_oracle.md` freeze policy.

**导出：** `{ analyzeForce, WEIGHTS }`

**签名：**
```js
analyzeForce(bazi: Object) → Object
```

**bazi 输入：**
```js
{ yearGan, yearZhi, monthGan, monthZhi, dayGan, dayZhi, hourGan, hourZhi }
```

**返回：**
```js
{
  riZhu: string,
  scoresRaw: { [十神]: number },
  scoresNormalized: { [十神]: number },  // 0-10 尺度
  contributions: { [十神]: { tougan, deling, roots, adjustments } },
  dayStrength: '身强'|'中和'|'身弱',
  sameSideScore: number,   // 比劫+印 原始分合计
  otherSideScore: number,  // 食伤+财+官杀 原始分合计
  sameRatio: number,       // sameSide / total，0-1
  congCandidate: boolean,  // sameRatio <= 0.15
  pairs: { [组]: [{ name, score, raw }, ...] },
  relations: { [十神]: [{ gan, position, relation }] },
}
```

**权重配置（`WEIGHTS`）：**
```js
{
  tougan: 3.0,      // 透干
  deling: 4.0,      // 得令（月令本气）
  rootBenQi: 2.0,   // 地支本气根
  rootZhongQi: 1.0, // 地支中气根
  rootYuQi: 0.5,    // 地支余气根
  heDiscount: 0.4,  // 被合走后保留 40%
  keDiscount: 0.6,  // 被邻干克后保留 60%（定义存在，当前未见应用在克上）
}
```

**四步评分逻辑：**
1. **透干**：年干/月干/时干各 `+3.0`（日干本身跳过，计为比肩"本位"）
2. **得令**：月支本气天干对应十神 `+4.0`（月支本气已在得令算，根阶段跳过避免重复）
3. **根**：所有地支藏干按本气/中气/余气权重 × 藏干本身 weight 累加
4. **合调整**：用 `findGanHe()` 找天干合对，被合者得分 × 0.4（减到 40%）
   - `# NOTE: liLiang.js:105-117` — 关键：reduction 公式是 `scores[ss] * (1 - heDiscount) = scores[ss] * 0.6`，然后 `scores[ss] -= reduction`。这不是"乘 0.4"的语义，而是"减掉 60%" = 保留 40%。`adjustments[].reduction` 字段也被 oracle 固化（四舍五入到 0.1），port 必须精确匹配中间值，不能重写成 `scores[ss] *= 0.4`。

**归一化：** 最高原始分映射到 10，其余等比缩放，结果保留 1 位小数。

**身强弱判定阈值（`# NOTE: liLiang.js:136`）：**
- sameRatio >= 0.55 → 身强
- sameRatio <= 0.35 → 身弱
- 其余 → 中和

**外部依赖：** `./ganzhi`, `./shishen`, `./cangGan`, `./heKe`

**注意：** `keDiscount` 权重已定义但当前代码中**克的减分逻辑未实现**（TODO）。

---

### `ming/geJu.js` — 格局识别

**导出：** `{ identifyGeJu, SHI_SHEN_TO_GE }`

**签名：**
```js
identifyGeJu(bazi: Object) → Object
```

**bazi 输入：** 同 `analyzeForce`（只用 `yearGan, monthGan, monthZhi, dayGan, hourGan`）

**返回：**
```js
{
  monthZhi: string,
  category: '四仲'|'四孟'|'四库',
  benQi: string,             // 月支本气天干
  benQiShiShen: string,      // 本气对日主的十神
  candidates: Array<{ name, source, via, shishen?, note? }>,
  mainCandidate: Object,     // candidates[0]
  decisionNote: string,      // 决策过程文字说明
  tougans: string[],         // 年干/月干/时干（非日主位）
  touInMonth: Array<{ gan, weight, role }>,  // 月支藏干中透出天干的子集
}
```

**格局识别规则（子平真诠）：**
1. **建禄/月刃格**（月令本气 = 日主比肩/劫财）：框架名定为建禄/月刃，但须从其他透干十神取实际用神
2. **四仲月**（子午卯酉）：月令本气单一，直接取格（无论是否透干）
3. **四孟月**（寅申巳亥）：本气或中气透干优先；都不透则取本气；仅余气透干时次要标注
4. **四库月**（辰戌丑未）：必须透干方可取格；无透干则输出"格局不清"，注"待刑冲开库"

**SHI_SHEN_TO_GE 映射表：**
```js
{ 正官:'正官格', 七杀:'七杀格', 正财:'正财格', 偏财:'偏财格',
  正印:'正印格', 偏印:'偏印格', 食神:'食神格', 伤官:'伤官格',
  比肩:'建禄格', 劫财:'月刃格' }
```

**外部依赖：** `./ganzhi`（`ZHI_CATEGORY`），`./cangGan`，`./shishen`

---

### `ming/heKe.js` — 天干合、地支冲/合/会

**导出：**
```js
GAN_HE, ZHI_LIU_HE, ZHI_CHONG_PAIRS, SAN_HE_JU, SAN_HUI,
findGanHe, findZhiRelations, isChong, isGanHe,
```

**签名：**
```js
findGanHe(gans: string[]) → Array<{ a, b, idx_a, idx_b, wuxing }>
findZhiRelations(zhis: string[]) → { liuHe, chong, sanHe, banHe, sanHui }
isChong(a: string, b: string) → boolean
isGanHe(a: string, b: string) → boolean
```

**天干五合（`GAN_HE`，双向键）：**
- 甲己合土、乙庚合金、丙辛合水、丁壬合木、戊癸合火

**地支六合（`ZHI_LIU_HE`，双向键）：**
- 子丑合土、寅亥合木、卯戌合火、辰酉合金、巳申合水、午未合日月（`null`，不化五行）

**地支六冲（`ZHI_CHONG_PAIRS`，数组）：**
- 子午、丑未、寅申、卯酉、辰戌、巳亥

**三合局（`SAN_HE_JU`）：**
- 申子辰水局（main:子）、亥卯未木局（main:卯）、寅午戌火局（main:午）、巳酉丑金局（main:酉）

**三会（`SAN_HUI`）：**
- 亥子丑北方水、寅卯辰东方木、巳午未南方火、申酉戌西方金

**半合：** `findZhiRelations` 内自动检测，条件 = 三合三支中命中 2 支且含 main 支

**外部依赖：** 无

---

### `ming/analyze.js` — 命理层主入口

**导出：** `{ analyze }`

**签名：**
```js
analyze(paipanResult: Object) → Object
```

**输入：** `paipan()` 的完整返回对象（用 `sizhu` 字段解析四柱）

**返回：**
```js
{
  bazi: { yearGan, yearZhi, monthGan, monthZhi, dayGan, dayZhi, hourGan, hourZhi },
  shiShen: {
    year:  { gan, ss },
    month: { gan, ss },
    day:   { gan, ss: '日主' },   // 日主固定标'日主'
    hour:  { gan, ss } | null,   // hourUnknown 时为 null
  },
  zhiDetail: {
    year:  { zhi, cangGan: [{ gan, weight, role, ss }] },
    month: ...,
    day:   ...,
    hour:  ...,   // hourUnknown 时该字段缺失
  },
  force: {          // analyzeForce() 结果的子集
    dayStrength, sameSideScore, otherSideScore, sameRatio,
    congCandidate, scores, pairs, relations, contributions,
  },
  geJu: Object,     // identifyGeJu() 完整返回
  ganHe: {
    all: [...],
    withRiZhu: [...],   // 只含涉及日主的合
  },
  zhiRelations: Object,  // findZhiRelations() 完整返回
  notes: Array<Object>,  // 自动生成的 LLM 提醒
}
```

**notes 自动生成规则（`buildNotes`）：**
| 触发条件 | type | 意图 |
|----------|------|------|
| 某比劫/食伤/财/官杀/印对子得分差 > 3 | `pair_mismatch` | 防"笼统称旺/弱" |
| 食伤 ≤ 2 且偏财 ≥ 6 | `alt_expression_channel` | 防"断无表达出口" |
| 食伤 ≤ 2 且比劫 ≥ 4 | `alt_autonomy_channel` | 防"断无自主" |
| 日主与偏财/正财有合 | `rizhu_he_cai` | 财带情维度 |
| 日主与正官/七杀有合 | `rizhu_he_guan` | 关系主动融合 |
| 地支有冲 | `zhi_chong` | 突发/变动 |
| sameRatio ≤ 0.15 | `cong_candidate` | 从格候选 |
| 四库月无透干 | `geju_unclear` | 格局不清 |

**调用链（不在 `paipan.js` 内调用）：**
- `server.js` → `analyze(paipanResult)` → [shishen, cangGan, heKe, liLiang, geJu]
- 也在 `paipan-engine/test3.js` 中调用（测试用途）

**外部依赖：** `./shishen`, `./cangGan`, `./heKe`, `./liLiang`, `./geJu`（不依赖 `ganzhi.js` 直接，通过上述模块间接）

---

## 模块依赖图

```
paipan.js
├── solarTime.js           (无依赖)
├── chinaDst.js            (无依赖)
├── ziHourAndJieqi.js      → lunar-javascript
└── cities.js              → fs/path + cities-data.json

ming/analyze.js            (调用方: server.js, test3.js)
├── ming/shishen.js        → ganzhi.js
├── ming/cangGan.js        (无依赖)
├── ming/heKe.js           (无依赖)
├── ming/liLiang.js        → ganzhi.js, shishen.js, cangGan.js, heKe.js
└── ming/geJu.js           → ganzhi.js, cangGan.js, shishen.js

ming/ganzhi.js             (无依赖, 被上述多模块引用)
```

---

## 已知 Edge Case 核查

以下逐条核查计划草稿列出的 10 个 edge case，以实际源码为准：

### EC-1：hour = -1（未知时辰）
**状态：已验证。**
`paipan.js:53` 将 hour=-1 映射为 `h = 12` 占位，并设 `hourUnknown = true`。后续所有需要时辰的字段返回 `null`：时柱、时干十神、时支藏干、时柱纳音。大运仍可计算（大运只依赖月柱和性别）。

### EC-2：ziConvention = 'late'（晚子时派）
**状态：已验证，计划草稿表述"不确定"有误——功能已完整实现。**
`ziHourAndJieqi.js:24`：只有 `hour === 23` 时才触发转换，加 1 小时进入次日。其他小时透传，`converted: false`。

### EC-3：useTrueSolarTime = false
**状态：已验证。**
`paipan.js:83`：`if (useTrueSolarTime && ...)` 短路，完全跳过真太阳时步骤。

### EC-4：城市不识别
**状态：已验证且有明确 warning。**
`paipan.js:80`：城市不识别时推送 warning 文字"未识别城市'XX'..."，`meta.cityUnknown = true`，不静默跳过。

### EC-5：DST 边界（1986/5/4 02:00 等精确时刻）
**状态：已验证。**
`chinaDst.js:40-44`：区间 `[start日 02:00, end日 02:00)` 半开区间。`isChinaDst` 对分钟不敏感（只传 hour）——极精确的 02:00 本身处于边界，代码计算为"在 DST 内"（`ts >= startTs`）。若出生恰在 02:00，减 1 小时后变 01:00，逻辑正确。

### EC-6：节气交界 ±120 分钟警告
**状态：已验证。**
`ziHourAndJieqi.js:51`：默认阈值 `thresholdMinutes = 120`，warning 文字包含节气名、时间、相差分钟数。`paipan.js:114`：`if (jq.isNearBoundary) warnings.push(jq.hint)` 加入 warnings 数组。

### EC-7：longitude 直接传入（优先于 city）
**状态：已验证。**
`paipan.js:72-76`：`if (lng == null && city)` 才查城市坐标，longitude 有值则直接用，不查 cities。

### EC-8：overseas 城市（新加坡、纽约等）
**状态：已验证。**
`cities.js:29-56`：`OVERSEAS` 常量定义了 22 个海外城市，用 `Object.assign(RAW, OVERSEAS)` 并入主数据。

### EC-9：月令得令分与根分重复计算
**状态：已验证，代码已去重。**
`liLiang.js:92`：月支在根阶段时跳过本气（`if (pos === '月支' && role === '本气') continue`），避免月支本气同时计入得令分和根分。

### EC-10：从格候选阈值
**状态：已验证。**
`liLiang.js:141`：`sameRatio <= 0.15` 时 `congCandidate = true`，在 `analyze.js` 的 notes 中触发 `cong_candidate` 提醒。

---

## Edge Case 输入覆盖清单（for Task 5）

下表是 Task 5（写 `birth_inputs.json` 的 50 条用例）的覆盖起点——每行可直接作为 JSON 数组中的一条。所有字段按 `paipan(opts)` 的签名命名；未写的字段用默认值。

| EC# | 触发条件 | 最小输入示例 | 断言 |
|-----|---------|-------------|------|
| EC-1 | hour = -1（未知时辰） | `{year:1990,month:6,day:15,hour:-1,minute:0,gender:"male"}` | `hourUnknown=true`；`sizhu.hour=null`；`shishen.hour=null`；`cangGan.hour=null`；`naYin.hour=null`；`dayun.list.length=8` |
| EC-2 | 晚子时派 + hour=23 | `{year:2024,month:3,day:15,hour:23,minute:30,ziConvention:"late",longitude:116.4,gender:"male"}` | `meta.corrections` 含 `type:"late_zi"`；`solarCorrected` 对应次日（2024-03-16）0:30 附近；日柱为次日干支 |
| EC-3 | useTrueSolarTime=false | `{year:1990,month:6,day:15,hour:10,minute:0,city:"长沙",useTrueSolarTime:false,gender:"female"}` | `meta.corrections` 不含 `type:"true_solar_time"`；`solarCorrected` 时分与输入完全一致 |
| EC-4 | 城市不识别 | `{year:1990,month:6,day:15,hour:10,minute:0,city:"火星基地一号",useTrueSolarTime:true,gender:"male"}` | `warnings` 含"未识别城市" 字样；`meta.cityUnknown=true`；`meta.corrections` 不含 true_solar_time |
| EC-5 | DST 边界（1988-05 区间内） | `{year:1988,month:6,day:10,hour:10,minute:0,longitude:116.4,gender:"male"}` | `meta.corrections[0].type="china_dst"`；`warnings` 含"夏令时"字样；修正后 hour=9 |
| EC-6 | 节气交界 ±120 分钟 | `{year:2024,month:2,day:4,hour:17,minute:0,longitude:116.4,gender:"male"}` | `meta.jieqiCheck.isNearBoundary=true`；`meta.jieqiCheck.jieqi="立春"`；`warnings` 含节气提示 |
| EC-7 | longitude 直接提供 | `{year:1990,month:6,day:15,hour:10,minute:0,longitude:113.0,gender:"male"}` | `meta.corrections` 中 `longitude=113.0`；city 字段可缺省，不走城市查询 |
| EC-8 | 海外城市（新加坡） | `{year:1990,month:6,day:15,hour:10,minute:0,city:"新加坡",gender:"male"}` | `meta.corrections` 含 true_solar_time，且 `longitude≈103.82`；`resolvedCity="新加坡"` |
| EC-9 | 月令得令+根去重验证 | `{year:1984,month:3,day:5,hour:12,minute:0,longitude:116.4,gender:"male"}`（甲子年丙寅月甲辰日庚午时：月支寅本气甲） | `force.contributions["比肩"].deling.benQi="甲"`；`force.contributions["比肩"].roots` 不含 `{pos:"月支", role:"本气"}` 的条目（去重生效） |
| EC-10 | 从格候选（sameRatio≤0.15） | `{year:1990,month:10,day:15,hour:10,minute:0,longitude:116.4,gender:"female"}`（示例候选；若该盘 sameRatio > 0.15 需替换为同类极弱的盘） | `force.congCandidate=true`；`force.sameRatio≤0.15`；`notes` 含 `type:"cong_candidate"` |

**使用提示：**
- EC-9 / EC-10 的干支需要 oracle 生成后核对，若选定的输入未触发预期条件，替换成其他符合日期；目标是覆盖**逻辑分支**，不是具体某日某时。
- 每条建议加 `id: "EC-N"` 字段，方便断言脚本按 id 拿对应 fixture。
- 另建议补充常规无 edge 的"普通"输入若干条（Task 5 凑到 50 条），覆盖不同年份/性别/子时派组合。

---

## 计划草稿的错误/偏差总结

| 草稿内容 | 实际情况 |
|---------|---------|
| `getShiShen(dayGan, otherGan)` — 参数名 | 函数内用 `riZhu`/`gan`，顺序正确，无歧义 |
| `ming/analyze.js` 描述薄 | 实际是命理层主入口，含 `buildNotes` 自动生成 8 类 LLM 提醒 |
| `ming/liLiang.js` 描述薄 | 实际实现 4 步评分 + 归一化 + 身强弱判定 + congCandidate，含 WEIGHTS 可调 |
| `ming/geJu.js` 描述薄 | 实际完整实现子平真诠四分支（建禄月劫 / 四仲 / 四孟 / 四库） |
| `ming/heKe.js` 描述薄 | 实际实现天干五合、地支六合、六冲、三合、半合、三会，6 个导出 |
| "不确定 ziConvention 参数" | ziConvention 已完整实现（paipan.js line 43, 99-109） |
| getCangGan 签名未提权重 | 返回 `[{ gan, weight, role }]`，weight 由 liLiang.js 积分引用 |
| keDiscount 的克减分 | WEIGHTS 里有 keDiscount，但当前代码中对"被克"的减分逻辑未实现 |
