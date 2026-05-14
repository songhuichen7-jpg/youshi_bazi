// 命局能量曲线：确定性评分引擎。
// 5 层加权 → 一年的 y 值；冲合刑害 → 影线 / 波动幅度；神煞 → marker。
// 同一八字必产同一曲线。

import {
  GAN_WX,
  ZHI_WX,
  CANG_GAN,
  LIU_HE,
  LIU_CHONG,
  SAN_HE,
  SAN_XING,
  ZI_XING,
  LIU_HAI,
  buildScoringContext,
  elementScore,
  tenGodScore,
} from './wuxing.js';
import { computeShensha, pickPrimaryMarker } from './shensha.js';

// y 值五档分界线（amplification 后的最终 score 范围 [-3, +3]）。
const BAND_THRESHOLDS = [-1.8, -0.6, 0.6, 1.8];
const BAND_NAMES = ['extreme-low', 'low', 'mid', 'high', 'extreme-high'];

function bandFor(score) {
  for (let i = 0; i < BAND_THRESHOLDS.length; i++) {
    if (score < BAND_THRESHOLDS[i]) return BAND_NAMES[i];
  }
  return BAND_NAMES[BAND_NAMES.length - 1];
}

function checkZhiRelation(a, b) {
  if (!a || !b) return { type: 'none' };
  const lh = LIU_HE[a];
  if (lh && lh.partner === b) return { type: 'liuhe', wuxing: lh.wuxing };
  if (LIU_CHONG.has(a + b)) return { type: 'chong' };
  for (const xing of SAN_XING) {
    if (xing.includes(a) && xing.includes(b) && a !== b) return { type: 'xing' };
  }
  if (a === b && ZI_XING.has(a)) return { type: 'zixing' };
  if ((a === '子' && b === '卯') || (a === '卯' && b === '子')) return { type: 'xing' };
  if (LIU_HAI[a] === b) return { type: 'hai' };
  return { type: 'none' };
}

// 冲的"对位强度"（pairIntensity）：四正最强、四生次之、四库最弱。
//   子午 / 卯酉 = 1.00（四正：水火金木全冲）
//   寅申 / 巳亥 = 0.90（四生：本气冲但带余气）
//   辰戌 / 丑未 = 0.65（四库：互冲库杂气）
const FOUR_CARDINALS = new Set(['子', '午', '卯', '酉']);
const FOUR_BIRTHS = new Set(['寅', '申', '巳', '亥']);
function chongPairIntensity(a, b) {
  if (FOUR_CARDINALS.has(a) && FOUR_CARDINALS.has(b)) return 1.00;
  if (FOUR_BIRTHS.has(a) && FOUR_BIRTHS.has(b)) return 0.90;
  return 0.65; // 四库
}

/**
 * 评一个流年。
 *
 * 入参（全部确定性）：
 *   paipan:    { sizhu: { year, month, day, hour } }
 *   meta:      { yongshen: '火' | '金水' | ... }
 *   dayunStep: { gz, ss, startYear, endYear, years }
 *   year:      { year, gz, ss, current }
 *
 * 返回：
 *   {
 *     score, band,
 *     volatility,           // [0, 1]
 *     shensha, marker,
 *     relations,            // 自然语言关系列表
 *     yearGan, yearZhi,
 *     hasYongshen,          // false 时降级显示（不画 band 颜色）
 *   }
 */
export function scoreYear({ paipan, meta, dayunStep, year } = {}) {
  if (!paipan || !year || !year.gz) return null;
  const sizhu = paipan.sizhu || {};
  const dayCol = sizhu.day || '';
  const dayGan = dayCol[0] || '';
  const dayZhi = dayCol[1] || '';
  const monthZhi = (sizhu.month || '')[1] || '';
  const yearGan = year.gz[0] || '';
  const yearZhi = year.gz[1] || '';
  if (!dayGan || !yearGan || !yearZhi) return null;

  // ctx 含 dayMasterElement / dayStrengthClass / yongshenSet —— 下面所有 elementScore
  // 都吃同一个 ctx，避免每个 helper 自己重新派生造成不一致。
  const ctx = buildScoringContext(paipan, meta);

  // ── L0: 大运背景 ───────────────────────
  // 大运干支自身的十神评分作为这十年的"底色能量"。
  // 现在用 tenGodScore（按具体天干 + 阴阳极性走 10 类十神细分），不再用粗
  // 同党/异党。藏干天干用 cg.gan 直接进 tenGodScore。
  const dayunGanLocal = (dayunStep?.gz || '')[0] || '';
  const dayunZhiLocal = (dayunStep?.gz || '')[1] || '';
  let l0 = 0;
  if (dayunGanLocal && dayunZhiLocal) {
    l0 += 0.4 * tenGodScore(dayunGanLocal, ctx);
    const dayunCg = CANG_GAN[dayunZhiLocal] || [];
    dayunCg.forEach((cg, i) => {
      const w = i === 0 ? 0.3 : i === 1 ? 0.1 : 0.05;
      l0 += w * cg.weight * tenGodScore(cg.gan, ctx);
    });
  }

  // ── L1: 流年自身 ───────────────────────
  let l1 = 0;
  l1 += 0.4 * tenGodScore(yearGan, ctx);
  const cgList = CANG_GAN[yearZhi] || [];
  cgList.forEach((cg, i) => {
    const positionWeight = i === 0 ? 0.3 : i === 1 ? 0.1 : 0.05;
    l1 += positionWeight * cg.weight * tenGodScore(cg.gan, ctx);
  });

  // ── L2: 日主关系（流年支 vs 日支 / 月令）──
  //
  // 方向性公式（参 GPT 深研建议）:
  //   delta = pairIntensity × targetImportance × baseMagnitude × joySign
  //
  // joySign：
  //   冲 → 看被冲支的喜忌方向 (冲喜神为凶, 冲忌神为吉)
  //   合 → 看化合后元素的喜忌 (合化为喜则吉, 合化为忌则凶)
  //   刑/害 → 看被刑/被害支的喜忌方向, 通常负向, 刑到喜神更重
  let l2 = 0;
  let volatility = 0;
  const relations = [];

  const dayRel = checkZhiRelation(yearZhi, dayZhi);
  if (dayRel.type === 'liuhe') {
    // 化合后五行的喜忌方向, 系数 0.3 不变
    l2 += 0.3 * elementScore(dayRel.wuxing, ctx);
    relations.push({ kind: 'liuhe', text: `${yearZhi}${dayZhi}六合化${dayRel.wuxing}` });
  } else if (dayRel.type === 'chong') {
    // 冲日支：joySign 由被冲方（日支）的本气五行决定。冲消除目标 → 反号。
    const targetWx = ZHI_WX[dayZhi];
    const targetJoy = targetWx ? elementScore(targetWx, ctx) : 0;
    const intensity = chongPairIntensity(yearZhi, dayZhi);
    const TARGET_IMPORTANCE_DAY = 0.75;
    // 冲喜神 (targetJoy>0) → 负 delta；冲忌神 (targetJoy<0) → 正 delta
    l2 -= intensity * TARGET_IMPORTANCE_DAY * 0.30 * targetJoy;
    volatility += intensity * 0.45;
    relations.push({ kind: 'chong', text: `${yearZhi}冲日支${dayZhi}` });
  } else if (dayRel.type === 'xing' || dayRel.type === 'zixing') {
    // 刑通常负向。joySign 仅作幅度调节：刑到喜神更重 (×1)，刑到忌神减半 (×0.5)。
    const targetWx = ZHI_WX[dayZhi];
    const targetJoy = targetWx ? elementScore(targetWx, ctx) : 0;
    const sign = targetJoy >= 0 ? 1 : 0.5;
    l2 -= 0.15 * sign;
    volatility += 0.20;
    relations.push({ kind: 'xing', text: `${yearZhi}${dayZhi}${dayRel.type === 'zixing' ? '自刑' : '相刑'}` });
  } else if (dayRel.type === 'hai') {
    l2 -= 0.10;
    relations.push({ kind: 'hai', text: `${yearZhi}${dayZhi}相害` });
  }

  // 冲月令（提纲）— targetImportance 1.00（月令是格局核心）
  if (monthZhi && monthZhi !== dayZhi) {
    const monthRel = checkZhiRelation(yearZhi, monthZhi);
    if (monthRel.type === 'chong') {
      const targetWx = ZHI_WX[monthZhi];
      const targetJoy = targetWx ? elementScore(targetWx, ctx) : 0;
      const intensity = chongPairIntensity(yearZhi, monthZhi);
      l2 -= intensity * 1.00 * 0.30 * targetJoy;
      volatility += intensity * 0.65;
      relations.push({ kind: 'chong-tigang', text: `冲提纲（${yearZhi}冲月令${monthZhi}）` });
    }
  }

  // ── L3: 大运 × 流年 对冲 ─────────────
  // 现在 polarity 也用 tenGodScore 直接打分（按具体天干，不通过 element 代理）。
  let conflictPenalty = 0;
  const dayunGan = dayunGanLocal;
  const dayunZhi = dayunZhiLocal;
  if (dayunGan && dayunZhi) {
    const dayunPolarity = tenGodScore(dayunGan, ctx) + elementScore(ZHI_WX[dayunZhi], ctx);
    const yearPolarity = tenGodScore(yearGan, ctx) + elementScore(ZHI_WX[yearZhi], ctx);
    if (dayunPolarity * yearPolarity < -0.4) {
      conflictPenalty = -0.15;
      volatility += 0.30;
      relations.push({ kind: 'duichong', text: `大运${dayunStep.gz}与流年${year.gz}对冲` });
    }
  }

  // ── L4: 命局共振（流年支 + 命局四支 三合 / 半合 / 六合）─
  // 三合系数 0.25 / 半合 0.12 / 六合 0.15，全部 × 化合后元素的 elementScore。
  let l4 = 0;
  const sizhuZhi = [
    (sizhu.year || '')[1],
    (sizhu.month || '')[1],
    (sizhu.day || '')[1],
    (sizhu.hour || '')[1],
  ].filter(Boolean);

  for (const sh of SAN_HE) {
    if (!sh.zhi.includes(yearZhi)) continue;
    const others = sh.zhi.filter((z) => z !== yearZhi);
    const matched = others.filter((z) => sizhuZhi.includes(z));
    if (matched.length === 2) {
      l4 += 0.25 * elementScore(sh.wuxing, ctx);
      relations.push({ kind: 'sanhe', text: `三合${sh.zhi.join('')}化${sh.wuxing}` });
    } else if (matched.length === 1) {
      l4 += 0.12 * elementScore(sh.wuxing, ctx);
      relations.push({ kind: 'banhe', text: `半合${[...matched, yearZhi].join('')}→${sh.wuxing}` });
    }
  }

  for (const z of sizhuZhi) {
    if (z === dayZhi) continue; // 已计入 L2
    const lh = LIU_HE[yearZhi];
    if (lh && lh.partner === z) {
      l4 += 0.15 * elementScore(lh.wuxing, ctx);
      relations.push({ kind: 'liuhe-mingju', text: `${yearZhi}${z}六合化${lh.wuxing}` });
    }
  }

  // ── L5: 神煞修正 ────────────────────
  const sizhuGzList = ['year', 'month', 'day', 'hour']
    .map((k) => sizhu[k])
    .filter(Boolean);
  const shensha = computeShensha({
    dayGan,
    dayZhi,
    dayGz: sizhu.day || '',
    yearZhi,
    yearGz: year.gz,
    sizhuGz: sizhuGzList,
  });
  // 神煞修正（方向性 / context-aware） — 参《三命通会》"贵人无气，虽有如无"。
  let l5 = 0;
  if (shensha.includes('天乙贵人')) {
    // 仅当 流年支本气五行 对日主是喜方 (elementScore > 0) 才计 +0.10。
    // 临忌神 / 死绝 → 不加分（只剩 marker 提示）。
    const benqiGan = (CANG_GAN[yearZhi] || [])[0]?.gan;
    const benqiWx = benqiGan ? GAN_WX[benqiGan] : '';
    if (benqiWx && elementScore(benqiWx, ctx) > 0) {
      l5 += 0.10;
    }
  }
  if (shensha.includes('伏吟')) {
    l5 -= 0.15;
    volatility += 0.30;
  }
  if (shensha.includes('空亡')) {
    // 流年 element 是用神 + 该年落空亡 → 用神落空, -0.15。
    // 其它情形空亡只 marker, volatility +0.10。
    const yearWx = ZHI_WX[yearZhi];
    if (yearWx && ctx.yongshenSet && ctx.yongshenSet.has(yearWx)) {
      l5 -= 0.15;
    }
    volatility += 0.10;
  }

  // ── 汇总 ─────────────────────────────
  // tanh 平滑压缩 → [-3, +3]，避免硬 clamp 把大量年份压在五档边界上。
  // 1/1.8 控制斜率，让 raw ~ ±2.0 时映射到 ±2.3 (顺/阻 满档边缘)、raw ~ ±3.5
  // 时映射到 ~±2.8（接近 极佳 / 极险）、再大也只渐近不撞顶。
  const raw = l0 + l1 + l2 + l4 + l5 + conflictPenalty;
  const score = 3 * Math.tanh(raw / 1.8);

  return {
    score,
    band: bandFor(score),
    volatility: Math.min(1, volatility),
    shensha,
    marker: pickPrimaryMarker(shensha),
    relations,
    yearGan,
    yearZhi,
    yearGz: year.gz,
    yearShishen: year.ss || '',
    hasYongshen: ctx.hasYongshen,
  };
}

/**
 * 评一步大运（聚合该运 10 个流年）。
 * 大运 K 的 y 值 = 10 年的均值。
 * 大运的影线 = 10 年中 score 最大-最小 的差（年内反差）。
 */
export function scoreDayun({ paipan, meta, dayunStep } = {}) {
  if (!dayunStep || !dayunStep.years || dayunStep.years.length === 0) return null;
  const yearScores = dayunStep.years
    .map((y) => scoreYear({ paipan, meta, dayunStep, year: y }))
    .filter(Boolean);
  if (yearScores.length === 0) return null;

  const avg = yearScores.reduce((s, y) => s + y.score, 0) / yearScores.length;
  let minScore = Infinity;
  let maxScore = -Infinity;
  let peakYearIdx = -1;
  let troughYearIdx = -1;
  yearScores.forEach((y, i) => {
    if (y.score > maxScore) { maxScore = y.score; peakYearIdx = i; }
    if (y.score < minScore) { minScore = y.score; troughYearIdx = i; }
  });
  const avgVolatility = yearScores.reduce((s, y) => s + y.volatility, 0) / yearScores.length;

  // 大运层主导神煞 — 出现 ≥ 2 次的，最多取 1 个。
  const counter = {};
  yearScores.forEach((y) => y.shensha.forEach((s) => { counter[s] = (counter[s] || 0) + 1; }));
  const dominantShensha = Object.entries(counter)
    .filter(([, n]) => n >= 2)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 2)
    .map(([s]) => s);

  // peak/trough 年标记 — 只在 score ≥ +1 或 ≤ -1 且超过平均 0.5 时才标，
  // 平淡大运不假装有突出年份。
  const peakYear = yearScores[peakYearIdx];
  const troughYear = yearScores[troughYearIdx];
  const hasPeakYear = peakYear && peakYear.score >= 1.0 && peakYear.score - avg >= 0.5;
  const hasTroughYear = troughYear && troughYear.score <= -1.0 && avg - troughYear.score >= 0.5;
  if (hasPeakYear) peakYear.isPeakYear = true;
  if (hasTroughYear) troughYear.isTroughYear = true;

  return {
    score: avg,
    band: bandFor(avg),
    minScore,
    maxScore,
    peakYearIdx: hasPeakYear ? peakYearIdx : -1,
    troughYearIdx: hasTroughYear ? troughYearIdx : -1,
    volatility: Math.min(1, avgVolatility),
    range: maxScore - minScore, // 年内反差幅度
    shensha: dominantShensha,
    marker: pickPrimaryMarker(dominantShensha),
    yearScores,
    gz: dayunStep.gz,
    ss: dayunStep.ss,
    startYear: dayunStep.startYear,
    endYear: dayunStep.endYear,
    age: dayunStep.age,
    current: !!dayunStep.current,
    hasYongshen: yearScores[0].hasYongshen,
  };
}

/**
 * 一次性评所有大运 — 给主组件用。
 *
 * 后处理：标出"主峰"——最高分大运。规则：
 *   · score 必须 > 0.6（在"顺"档之上），否则命途整体平淡，不标
 *   · 严格唯一最高（并列时取最后一个，即更晚的运 — 老年高峰是更常见诉求）
 *   · 在 result[i] 上挂 isPeak: true
 */
export function scoreAllDayun({ paipan, meta, dayun } = {}) {
  if (!Array.isArray(dayun) || dayun.length === 0) return [];
  const scored = dayun
    .map((step) => scoreDayun({ paipan, meta, dayunStep: step }))
    .filter(Boolean);

  const PEAK_THRESHOLD = 0.6;
  let peakIdx = -1;
  let peakScore = -Infinity;
  for (let i = 0; i < scored.length; i++) {
    const s = scored[i].score;
    if (s > PEAK_THRESHOLD && s >= peakScore) {
      peakScore = s;
      peakIdx = i;
    }
  }
  if (peakIdx >= 0) scored[peakIdx].isPeak = true;
  return scored;
}

export { bandFor, BAND_NAMES };
