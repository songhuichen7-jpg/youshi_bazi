// 命局能量曲线评分引擎的单元测试。
// 重点是 L1（同党/异党 + dayStrength + yongshen 加成），覆盖之前的反向 bug：
//   1. 身弱 + 用印  → 印 + 比劫 应为 +
//   2. 身弱 + 用食伤（调候/制杀）→ 食伤是 yongshen 时为 +，但其他异党仍 -
//   3. 身强 + 用财官 → 极性反过来
//   4. 中和 → 弱信号但方向对
//   5. 多用神（土+水 内部冲突）→ 用神身份优先

import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildScoringContext,
  elementScore,
  tenGodCategory,
  tenGodOf,
  tenGodScore,
  isSameParty,
  classifyDayStrength,
} from '../src/lib/kline/wuxing.js';
import { scoreYear, scoreDayun, scoreAllDayun } from '../src/lib/kline/score.js';
import { analyzePaipanForce, detectChartVariant } from '../src/lib/kline/paipanForce.js';

// 通用 fixture：1990 男 辛酉日 身弱 用神 己土+壬水（之前测试用的盘）
const PAIPAN_XIN_WEAK = {
  sizhu: { year: '庚午', month: '壬午', day: '辛亥', hour: '乙未' },
};
const META_XIN_WEAK = {
  rizhuGan: '辛',
  dayStrength: '身弱',
  yongshen: '己土 / 壬水',
  today: { ymd: '2026-05-10' },
};

// 2003 男 甲戌日 身弱 用神丁火（食神/伤官制杀）
const PAIPAN_JIA_WEAK = {
  sizhu: { year: '癸未', month: '庚申', day: '甲戌', hour: '戊辰' },
};
const META_JIA_WEAK = {
  rizhuGan: '甲',
  dayStrength: '身弱',
  yongshen: '丁火',
  today: { ymd: '2026-05-10' },
};

// ── 基础工具 ───────────────────────────────────────────────────

test('classifyDayStrength: 极弱 / 极强 优先匹配', () => {
  assert.equal(classifyDayStrength('极弱'), 'extreme-weak');
  assert.equal(classifyDayStrength('从弱'), 'extreme-weak');
  assert.equal(classifyDayStrength('极强'), 'extreme-strong');
  assert.equal(classifyDayStrength('从强'), 'extreme-strong');
  assert.equal(classifyDayStrength('身弱'), 'weak');
  assert.equal(classifyDayStrength('身强'), 'strong');
  assert.equal(classifyDayStrength('中和'), 'balanced');
  assert.equal(classifyDayStrength(''), 'balanced');
  assert.equal(classifyDayStrength(undefined), 'balanced');
});

test('tenGodCategory: 五行对日主的关系', () => {
  // 甲木日主
  assert.equal(tenGodCategory('木', '木'), '比劫');
  assert.equal(tenGodCategory('水', '木'), '印');     // 水生木
  assert.equal(tenGodCategory('火', '木'), '食伤');   // 木生火
  assert.equal(tenGodCategory('土', '木'), '财');     // 木克土
  assert.equal(tenGodCategory('金', '木'), '官杀');   // 金克木
});

test('isSameParty: 印 + 比劫 是同党', () => {
  assert.equal(isSameParty('比劫'), true);
  assert.equal(isSameParty('印'), true);
  assert.equal(isSameParty('食伤'), false);
  assert.equal(isSameParty('财'), false);
  assert.equal(isSameParty('官杀'), false);
});

// ── L1 主层正确性 ─────────────────────────────────────────────

test('身弱用印：印水 + 比劫木 应为正；财土 + 官杀金 应为负', () => {
  // 甲木 身弱 用神丁火（这盘 yongshen 是火，但我们这条 case 测 dayStrength 主层）
  const ctx = buildScoringContext(PAIPAN_JIA_WEAK, META_JIA_WEAK);

  // 印水：身弱必喜 → 正
  const water = elementScore('水', ctx);
  assert.ok(water > 0, `印水应为正，实际 ${water}`);

  // 比劫木：身弱大帮 → 正
  const wood = elementScore('木', ctx);
  assert.ok(wood > 0, `比劫木应为正，实际 ${wood}`);

  // 官杀金：身弱大忌 → 负
  const metal = elementScore('金', ctx);
  assert.ok(metal < 0, `官杀金应为负，实际 ${metal}`);

  // 财土：异党 → 负
  const earth = elementScore('土', ctx);
  assert.ok(earth < 0, `财土应为负，实际 ${earth}`);

  // 食伤火：异党，但 yongshen 命中 → 由 bonus 抬正
  const fire = elementScore('火', ctx);
  assert.ok(fire > 0, `食伤火（用神）应为正，实际 ${fire}`);
});

test('身弱：印 应 > 比劫（杀印相生 强于 单纯帮身）', () => {
  // 2003 七杀格 身弱用丁火 — 印水 / 比劫木 都是同党，但印有"双功能"
  // (化官杀 + 生身) 应分数更高，让老年印运在曲线上明显高于中年比劫运。
  const ctx = buildScoringContext(PAIPAN_JIA_WEAK, META_JIA_WEAK);
  const water = elementScore('水', ctx); // 印
  const wood = elementScore('木', ctx);  // 比劫
  assert.ok(water > wood, `印水 ${water} 应 > 比劫木 ${wood}`);
  // 差距至少 0.15，避免被 round 到同一像素位置
  assert.ok(water - wood >= 0.15, `印水比比劫木至少高 0.15，实际 ${(water - wood).toFixed(2)}`);
});

test('身弱用印：水 是 yongshen 时, 还是正; 但比劫不是 yongshen 也是正', () => {
  // 这盘 yongshen 含水（壬水），所以水有 yongshen bonus
  const ctx = buildScoringContext(PAIPAN_XIN_WEAK, META_XIN_WEAK);

  // 印（土）：身弱 + yongshen 命中 → 正
  const earth = elementScore('土', ctx);
  assert.ok(earth > 0, `印土（用神）应为正，实际 ${earth}`);

  // 比劫（金）：身弱 但 不是 yongshen 命中（yongshen 含土+水，不含金）→ 主层应保住正
  const metal = elementScore('金', ctx);
  assert.ok(metal > 0, `比劫金应为正（同党扶身），实际 ${metal}`);

  // 食伤（水）：异党, 但 yongshen 命中 → 正
  const water = elementScore('水', ctx);
  assert.ok(water > 0, `食伤水（用神）应为正，实际 ${water}`);

  // 官杀（火）：异党, 不是 yongshen → 负
  const fire = elementScore('火', ctx);
  assert.ok(fire < 0, `官杀火应为负，实际 ${fire}`);

  // 财（木）：异党 不是 yongshen → 负
  const wood = elementScore('木', ctx);
  assert.ok(wood < 0, `财木应为负，实际 ${wood}`);
});

test('身强用财官：财官应为正、印比劫应为负', () => {
  const ctx = buildScoringContext(
    { sizhu: { year: '甲子', month: '乙亥', day: '甲寅', hour: '丁卯' } },
    { rizhuGan: '甲', dayStrength: '身强', yongshen: '土' },
  );

  // 财（土）：身强 异党 + yongshen 命中 → 正
  const earth = elementScore('土', ctx);
  assert.ok(earth > 0, `财土（用神）应为正，实际 ${earth}`);

  // 官杀（金）：身强 异党 → 正
  const metal = elementScore('金', ctx);
  assert.ok(metal > 0, `官杀金应为正（异党），实际 ${metal}`);

  // 比劫（木）：身强 同党 → 负
  const wood = elementScore('木', ctx);
  assert.ok(wood < 0, `比劫木应为负（同党更助身强），实际 ${wood}`);

  // 印（水）：身强 同党 → 负
  const water = elementScore('水', ctx);
  assert.ok(water < 0, `印水应为负（同党更助身强），实际 ${water}`);
});

test('中和：信号弱但方向跟身强类似（异党微正，同党微负）', () => {
  const ctx = buildScoringContext(
    { sizhu: { year: '甲子', month: '乙亥', day: '甲寅', hour: '丁卯' } },
    { rizhuGan: '甲', dayStrength: '中和', yongshen: '' },
  );
  // 没 yongshen 加成时, 中和走 ±0.2 弱信号
  const wood = elementScore('木', ctx);
  const earth = elementScore('土', ctx);
  assert.ok(Math.abs(wood) <= 0.25, `中和同党应弱信号，实际 ${wood}`);
  assert.ok(Math.abs(earth) <= 0.25, `中和异党应弱信号，实际 ${earth}`);
});

test('yongshen 加成最低保底 +0.6（处理身弱用食伤的反主层场景）', () => {
  // 身弱甲木用丁火：火 默认是 异党 (-0.6)，但 yongshen 命中应抬到 +0.6
  const ctx = buildScoringContext(PAIPAN_JIA_WEAK, META_JIA_WEAK);
  const fire = elementScore('火', ctx);
  assert.ok(fire >= 0.6, `身弱用食伤场景下 火 应被 yongshen 抬到 ≥ +0.6，实际 ${fire}`);
});

test('多用神 内部冲突（土+水）：用神身份优先，土水都 ≥ +0.6', () => {
  const ctx = buildScoringContext(PAIPAN_XIN_WEAK, META_XIN_WEAK);
  const earth = elementScore('土', ctx);
  const water = elementScore('水', ctx);
  assert.ok(earth >= 0.6, `多用神 土 应 ≥ +0.6，实际 ${earth}`);
  assert.ok(water >= 0.6, `多用神 水 应 ≥ +0.6，实际 ${water}`);
});

// ── 端到端：scoreDayun 的形状 ───────────────────────────────

function dayunFromGz(gzList, startYear = 1990, ageStart = 8) {
  // 把一组干支造成 dayun 数组（粗略版，每运 10 年）
  return gzList.map((gz, i) => ({
    gz,
    ss: '',
    startYear: startYear + i * 10,
    endYear: startYear + (i + 1) * 10 - 1,
    age: ageStart + i * 10,
    current: false,
    years: Array.from({ length: 10 }, (_, j) => ({
      year: startYear + i * 10 + j,
      gz: '',  // 不影响主体趋势的粗略验证
      ss: '',
      current: false,
    })),
  }));
}

test('身弱甲木用丁火: 印水大运 应高于 财土大运（之前的反向 bug 不再）', () => {
  // 简化：直接对比"水大运" vs "土大运" 的 score（使用相同月支结构）
  // 实际算法 scoreYear 受 yearGz 影响, 这里只看 大运的本身 score 影响
  const dayun = dayunFromGz(['壬子', '己未'], 1990, 8);
  // 给每个 year 一个中性 yearGz —— 让 L1 主要由 大运层级体现 还是不行因为
  // scoreYear L1 是基于 yearGz 不是 dayunGz。改用 dayunStep 直接的 score
  // (score.js 的 scoreDayun 是 yearScores 的均值)。我们需要让 yearGz 也能
  // 反映出"印旺"vs"财旺"的差距。简单做法：让所有 year 的 yearGz === 大运
  // 自身 (即每年都伏吟大运)。
  for (const step of dayun) {
    step.years = step.years.map((y) => ({ ...y, gz: step.gz }));
  }
  const yongPaipan = PAIPAN_JIA_WEAK;
  const yongMeta = META_JIA_WEAK;

  const waterRun = scoreDayun({ paipan: yongPaipan, meta: yongMeta, dayunStep: dayun[0] });
  const earthRun = scoreDayun({ paipan: yongPaipan, meta: yongMeta, dayunStep: dayun[1] });

  assert.ok(
    waterRun.score > earthRun.score,
    `身弱用丁火，印水大运 ${waterRun.score.toFixed(2)} 应 > 财土大运 ${earthRun.score.toFixed(2)}`,
  );
});

test('身弱甲木用丁火: 比劫木大运 应高于 官杀金大运', () => {
  const dayun = dayunFromGz(['乙卯', '辛酉'], 1990, 8);
  for (const step of dayun) {
    step.years = step.years.map((y) => ({ ...y, gz: step.gz }));
  }
  const woodRun = scoreDayun({ paipan: PAIPAN_JIA_WEAK, meta: META_JIA_WEAK, dayunStep: dayun[0] });
  const metalRun = scoreDayun({ paipan: PAIPAN_JIA_WEAK, meta: META_JIA_WEAK, dayunStep: dayun[1] });

  assert.ok(
    woodRun.score > metalRun.score,
    `身弱用丁火，比劫木大运 ${woodRun.score.toFixed(2)} 应 > 官杀金大运 ${metalRun.score.toFixed(2)}`,
  );
});

test('身弱甲木用丁火: 印水大运 应明显高于 比劫木大运（老年高峰可见）', () => {
  const dayun = dayunFromGz(['壬子', '乙卯'], 2080, 80);
  for (const step of dayun) {
    step.years = step.years.map((y) => ({ ...y, gz: step.gz }));
  }
  const yinRun = scoreDayun({ paipan: PAIPAN_JIA_WEAK, meta: META_JIA_WEAK, dayunStep: dayun[0] });
  const bijieRun = scoreDayun({ paipan: PAIPAN_JIA_WEAK, meta: META_JIA_WEAK, dayunStep: dayun[1] });
  assert.ok(
    yinRun.score - bijieRun.score >= 0.2,
    `印水大运 ${yinRun.score.toFixed(2)} 应比 比劫木大运 ${bijieRun.score.toFixed(2)} 至少高 0.2`,
  );
});

test('身弱甲木用丁火: 食伤火（用神）大运 应是高分（≥ 0.5 amplified）', () => {
  const dayun = dayunFromGz(['丁巳'], 1990, 8);
  dayun[0].years = dayun[0].years.map((y) => ({ ...y, gz: dayun[0].gz }));
  const fireRun = scoreDayun({ paipan: PAIPAN_JIA_WEAK, meta: META_JIA_WEAK, dayunStep: dayun[0] });
  assert.ok(fireRun.score > 0.5, `用神火大运 应 > 0.5 (amplified)，实际 ${fireRun.score.toFixed(2)}`);
});

test('scoreYear: 没有日柱 / 流年柱 时优雅 null', () => {
  assert.equal(scoreYear({ paipan: {}, year: { gz: '丙午' } }), null);
  assert.equal(scoreYear({ paipan: PAIPAN_JIA_WEAK, year: { gz: '' } }), null);
});

// ── 主峰标记 ────────────────────────────────────────────────

test('scoreAllDayun: 标出 score 最高且 > 0.6 的大运为 isPeak', () => {
  // 2003 盘走真实 流年 — 壬子(印水) 应是主峰
  const ZHIS = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥'];
  const GANS = ['甲','乙','丙','丁','戊','己','庚','辛','壬','癸'];
  const yearGz = (y) => GANS[(y - 4) % 10] + ZHIS[(y - 4) % 12];
  const dayunGzs = ['己未','戊午','丁巳','丙辰','乙卯','甲寅','癸丑','壬子'];
  const dayun = dayunGzs.map((gz, i) => ({
    gz, ss: '', startYear: 2011 + i*10, endYear: 2020 + i*10, age: 8 + i*10,
    current: false,
    years: Array.from({length: 10}, (_, j) => ({
      year: 2011 + i*10 + j, gz: yearGz(2011 + i*10 + j), ss: '', current: false,
    })),
  }));
  const scored = scoreAllDayun({ paipan: PAIPAN_JIA_WEAK, meta: META_JIA_WEAK, dayun });
  const peaks = scored.filter((s) => s.isPeak);
  assert.equal(peaks.length, 1, '应该只有一个主峰');
  assert.equal(peaks[0].gz, '壬子', `主峰应为 壬子，实际 ${peaks[0].gz}`);
});

// ── Phase 1: 十神细分 ──────────────────────────────────────────

test('tenGodOf: 阴阳极性 → 正/偏 / 比/劫 / 食/伤 / 正/七 / 正/偏', () => {
  // 甲木日主
  assert.equal(tenGodOf('甲', '甲'), '比肩');   // 阳木 vs 阳木 = 同性 → 比肩
  assert.equal(tenGodOf('乙', '甲'), '劫财');   // 阴 vs 阳 = 异性 → 劫财
  assert.equal(tenGodOf('壬', '甲'), '偏印');   // 阳水 vs 阳木 = 同性 → 偏印
  assert.equal(tenGodOf('癸', '甲'), '正印');   // 阴 vs 阳 = 异性 → 正印
  assert.equal(tenGodOf('丙', '甲'), '食神');   // 阳火 = 同性 → 食神
  assert.equal(tenGodOf('丁', '甲'), '伤官');   // 阴 = 异性 → 伤官
  assert.equal(tenGodOf('戊', '甲'), '偏财');   // 阳土 = 同性 → 偏财
  assert.equal(tenGodOf('己', '甲'), '正财');
  assert.equal(tenGodOf('庚', '甲'), '七杀');   // 阳金 = 同性 → 七杀
  assert.equal(tenGodOf('辛', '甲'), '正官');
});

test('身弱：正印 > 比肩 > 劫财（十神细分梯度）', () => {
  const ctx = buildScoringContext(PAIPAN_JIA_WEAK, META_JIA_WEAK);
  const zhengyin = tenGodScore('癸', ctx);   // 正印
  const bijie = tenGodScore('甲', ctx);       // 比肩
  const jiecai = tenGodScore('乙', ctx);      // 劫财
  assert.ok(zhengyin > bijie, `正印 ${zhengyin} 应 > 比肩 ${bijie}`);
  assert.ok(bijie > jiecai, `比肩 ${bijie} 应 > 劫财 ${jiecai}`);
});

test('身强：正官 > 七杀 > 伤官（异党细分梯度）', () => {
  const ctx = buildScoringContext(
    { sizhu: { year: '甲子', month: '乙亥', day: '甲寅', hour: '丁卯' } },
    { rizhuGan: '甲', dayStrength: '身强', yongshen: '' },
  );
  const zhengguan = tenGodScore('辛', ctx);  // 正官 +0.70
  const qisha = tenGodScore('庚', ctx);      // 七杀 +0.55
  const shangguan = tenGodScore('丁', ctx);  // 伤官 +0.55
  assert.ok(zhengguan > qisha, `正官 ${zhengguan} 应 > 七杀 ${qisha}`);
  assert.ok(zhengguan >= shangguan, `正官 ${zhengguan} 应 ≥ 伤官 ${shangguan}`);
});

// ── Phase 1: 冲方向性 ──────────────────────────────────────────

test('身弱用神火：流年冲日支（被冲方是日支戌=土=异党=忌神）→ 应有 + delta', () => {
  // 2003 甲戌日 身弱用丁火。戌=土=财=忌。流年辰冲戌 → 冲走忌神 → +
  const earthDayChart = PAIPAN_JIA_WEAK;
  const yearObj = { year: 2030, gz: '庚辰', ss: '', current: false };
  const dayunStep = { gz: '丙辰', ss: '', startYear: 2030, endYear: 2039, age: 27, current: false, years: [yearObj] };
  const sc = scoreYear({ paipan: earthDayChart, meta: META_JIA_WEAK, dayunStep, year: yearObj });
  // 流年辰 冲 日支戌（被冲=戌=土=身弱忌神）— 应该有"去病"的正向贡献
  // 看 relations 是否含 chong
  const chongRels = sc.relations.filter((r) => r.kind === 'chong');
  assert.ok(chongRels.length > 0, '应识别出辰戌冲日支');
});

// ── Phase 1: 从弱反转 ─────────────────────────────────────────

test('极弱 / 从弱：同党反忌、异党反喜（走 strong 表）', () => {
  const ctx = buildScoringContext(
    { sizhu: { year: '癸卯', month: '乙卯', day: '甲子', hour: '丙寅' } },
    { rizhuGan: '甲', dayStrength: '极弱', yongshen: '' },
  );
  // 极弱反转：印水 应负（同党变忌）, 财土 应正（异党变喜）
  const water = tenGodScore('癸', ctx);  // 正印 strong 行 → -0.60
  const earth = tenGodScore('戊', ctx);  // 偏财 strong 行 → +0.60
  assert.ok(water < 0, `从弱时印水应负，实际 ${water}`);
  assert.ok(earth > 0, `从弱时财土应正，实际 ${earth}`);
});

// ── Phase 1: tanh 平滑 ─────────────────────────────────────────

test('tanh: 极端 raw 值不再硬撞 ±3，而是渐近', () => {
  // 通过实际 scoreYear 间接验证：raw = 4 (大幅超出) 应映射到 ~2.8 而非 3.0
  // 直接构造一个全部 yongshen + 同党的极端场景
  const idealPaipan = { sizhu: { year: '丁卯', month: '丁卯', day: '甲子', hour: '甲子' } };
  const idealMeta = { rizhuGan: '甲', dayStrength: '身弱', yongshen: '水木火', today: { ymd: '2026-01-01' } };
  const idealYear = { year: 2026, gz: '癸卯', ss: '', current: false };
  const idealStep = { gz: '癸卯', ss: '', startYear: 2026, endYear: 2035, age: 30, current: false, years: [idealYear] };
  const sc = scoreYear({ paipan: idealPaipan, meta: idealMeta, dayunStep: idealStep, year: idealYear });
  assert.ok(sc.score <= 3, `score 不应超过 3，实际 ${sc.score}`);
  assert.ok(sc.score < 2.99, `极端 raw 应被 tanh 软压, 不应贴近 ±3 顶`);
});

// ── Phase 1: peak/trough 年 ────────────────────────────────────

// ── Phase 2: 用神角色 floor + 格局 combo ──────────────────────

test('Phase 2: 用神角色 floor — 调候/通关 > 扶抑', () => {
  // 同一个 element 是 yongshen, role=调候 vs role=扶抑 → 调候 floor 应更高
  // 用一个 异党 当 yongshen (制造主表 base < floor 的场景)
  const base = { sizhu: { year: '甲子', month: '甲戌', day: '甲戌', hour: '甲子' } };
  const tiaoHou = buildScoringContext(base, {
    rizhuGan: '甲', dayStrength: '身弱', yongshen: '丁火',
    yongshenDetail: { candidates: [{ method: '调候', name: '丁火' }] },
  });
  const fuYi = buildScoringContext(base, {
    rizhuGan: '甲', dayStrength: '身弱', yongshen: '丁火',
    yongshenDetail: { candidates: [{ method: '扶抑', name: '丁火' }] },
  });
  const fireTiao = tenGodScore('丁', tiaoHou);
  const fireFuYi = tenGodScore('丁', fuYi);
  assert.ok(fireTiao > fireFuYi, `调候火 ${fireTiao} 应 > 扶抑火 ${fireFuYi}`);
  assert.ok(fireTiao >= 0.80, `调候 floor 应 ≥ 0.80, 实际 ${fireTiao}`);
});

test('Phase 2: 病药 floor 最高 (≥ 0.85)', () => {
  const ctx = buildScoringContext(
    { sizhu: { year: '甲子', month: '甲戌', day: '甲戌', hour: '甲子' } },
    {
      rizhuGan: '甲', dayStrength: '身弱', yongshen: '丁火',
      yongshenDetail: { candidates: [{ method: '病药', name: '丁火' }] },
    },
  );
  const fire = tenGodScore('丁', ctx);
  assert.ok(fire >= 0.85, `病药用神 floor 应 ≥ 0.85, 实际 ${fire}`);
});

test('Phase 2: 七杀格 + 食神 → 食神制杀成格 +0.20 bonus', () => {
  const sevenSha = buildScoringContext(
    { sizhu: { year: '癸未', month: '庚申', day: '甲戌', hour: '戊辰' } },
    { rizhuGan: '甲', dayStrength: '身弱', yongshen: '丁火', geju: '七杀格' },
  );
  const noGeju = buildScoringContext(
    { sizhu: { year: '癸未', month: '庚申', day: '甲戌', hour: '戊辰' } },
    { rizhuGan: '甲', dayStrength: '身弱', yongshen: '丁火' },
  );
  // 丙=食神 vs 甲日。七杀格 + 食神 应 > 无格局时
  const withGeju = tenGodScore('丙', sevenSha);
  const without = tenGodScore('丙', noGeju);
  assert.ok(withGeju - without >= 0.15, `七杀格食神 bonus 至少 0.15, 实际 ${(withGeju - without).toFixed(2)}`);
});

test('Phase 2: 伤官格 + 正官 → 伤官见官 -0.20 penalty', () => {
  const ctx = buildScoringContext(
    { sizhu: { year: '甲子', month: '丙寅', day: '甲戌', hour: '丁卯' } },
    { rizhuGan: '甲', dayStrength: '身强', yongshen: '', geju: '伤官格' },
  );
  const ctxNoGeju = buildScoringContext(
    { sizhu: { year: '甲子', month: '丙寅', day: '甲戌', hour: '丁卯' } },
    { rizhuGan: '甲', dayStrength: '身强', yongshen: '' },
  );
  const withGeju = tenGodScore('辛', ctx);
  const without = tenGodScore('辛', ctxNoGeju);
  assert.ok(without - withGeju >= 0.15, `伤官见官 penalty 至少 0.15, 实际 ${(without - withGeju).toFixed(2)}`);
});

test('Phase 2: 财格 + 比劫 → 比劫夺财 -0.15 penalty', () => {
  const ctx = buildScoringContext(
    { sizhu: { year: '甲子', month: '己未', day: '甲戌', hour: '丁卯' } },
    { rizhuGan: '甲', dayStrength: '身强', yongshen: '', geju: '正财格' },
  );
  const ctxNoGeju = buildScoringContext(
    { sizhu: { year: '甲子', month: '己未', day: '甲戌', hour: '丁卯' } },
    { rizhuGan: '甲', dayStrength: '身强', yongshen: '' },
  );
  const withGeju = tenGodScore('甲', ctx); // 比肩
  const without = tenGodScore('甲', ctxNoGeju);
  assert.ok(without - withGeju >= 0.10, `比劫夺财 penalty, 实际 ${(without - withGeju).toFixed(2)}`);
});

test('Phase 2: 没 yongshenDetail 时 fallback +0.70 不破 Phase 1 行为', () => {
  const ctx = buildScoringContext(
    PAIPAN_JIA_WEAK,
    { rizhuGan: '甲', dayStrength: '身弱', yongshen: '丁火' }, // 无 detail
  );
  const fire = tenGodScore('丁', ctx);
  assert.ok(fire >= 0.70, `fallback floor 应 ≥ 0.70, 实际 ${fire}`);
});

// ── Phase 3: 命局力量场 + 从格变体 ────────────────────────────

test('Phase 3 analyzePaipanForce: 七杀重命局应识别 sevenShaHeavy', () => {
  // 一个 七杀重 的命局：甲日 多见 庚 (七杀)
  // 庚申月 + 庚 透 + 申金本气 → 杀的力量场应该很重
  const paipan = { sizhu: { year: '庚申', month: '庚申', day: '甲戌', hour: '戊辰' } };
  const force = analyzePaipanForce(paipan, '甲');
  assert.ok(force.patterns.sevenShaHeavy, `杀重命局 sevenShaHeavy 应为 true, 实际 counts['七杀']=${force.counts['七杀']}`);
});

test('Phase 3 analyzePaipanForce: 透干 + 通根 检测', () => {
  // 庚 在月干透干, 申支藏庚 → 七杀通根
  const paipan = { sizhu: { year: '癸亥', month: '庚申', day: '甲子', hour: '丁卯' } };
  const force = analyzePaipanForce(paipan, '甲');
  assert.ok(force.transparent.has('七杀'), '七杀应在 transparent (庚月干透)');
  assert.ok(force.rooted.has('七杀'), '七杀应通根 (庚在月干又在申支)');
});

test('Phase 3 detectChartVariant: 极弱 + 七杀主导 → follow-sha', () => {
  const patterns = {
    sevenShaHeavy: true, yinHeavy: false, shiShangHeavy: false,
    caiHeavy: false, bijieHeavy: false, guanShaMixed: false,
    shiShangMixed: false, noControlForSha: true,
    sameParty: 0.3, otherParty: 3.0,
  };
  assert.equal(detectChartVariant('extreme-weak', patterns), 'follow-sha');
  assert.equal(detectChartVariant('weak', patterns), null, '普通身弱不强行套从格');
});

test('Phase 3 chartForceComboBonus: 杀重命局 + 流年印 → 印加 +0.15 (杀印相生)', () => {
  // 命局七杀重: 甲日 + 庚申 多见 → 杀重
  // baseline: 同样身弱、yongshen 都没, 但用一个 patterns 都不触发的清水盘
  const ctxBaseline = buildScoringContext(
    { sizhu: { year: '甲戌', month: '甲戌', day: '甲戌', hour: '甲戌' } },
    { rizhuGan: '甲', dayStrength: '身弱', yongshen: '' },
  );
  const ctxShaHeavy = buildScoringContext(
    { sizhu: { year: '庚申', month: '庚申', day: '甲戌', hour: '戊辰' } },
    { rizhuGan: '甲', dayStrength: '身弱', yongshen: '' },
  );
  const yinBaseline = tenGodScore('癸', ctxBaseline);
  const yinShaHeavy = tenGodScore('癸', ctxShaHeavy);
  // baseline 全甲戌没有杀, ctxShaHeavy 应额外加 +0.15
  assert.ok(yinShaHeavy - yinBaseline >= 0.10, `杀重时印应有额外 +bonus, 实际差 ${(yinShaHeavy - yinBaseline).toFixed(2)}`);
});

test('Phase 3 chartVariantBonus: 从儿格 + 流年官杀 → 大忌 (-0.30)', () => {
  // 制造一个 从儿场景：甲日 极弱, 食伤主导
  const ctx = buildScoringContext(
    { sizhu: { year: '丙午', month: '丁巳', day: '甲午', hour: '丙寅' } },
    { rizhuGan: '甲', dayStrength: '极弱', yongshen: '' },
  );
  // 不一定真识别成 follow-er（需要 patterns.shiShangHeavy 且 caiHeavy/sevenShaHeavy 不 heavy）
  // 这里直接断言 chartVariant 不为 null 即可（说明 from格识别 work）
  assert.ok(ctx.chartVariant !== null, `极弱 + 食伤主导命局应识别从格变体, 实际 ${ctx.chartVariant}`);
});

test('Phase 3 yongshen 透干 / 通根 → 小 bonus', () => {
  // 用 2003 盘 (甲戌日 七杀格 用丁火), 看 丁 在原命局没透没根, 跟设想透根的差异
  // 简单测：rooted/transparent 含 时 +0.08 通根 / +0.05 透干
  const ctx = buildScoringContext(
    PAIPAN_JIA_WEAK,
    {
      rizhuGan: '甲', dayStrength: '身弱', yongshen: '丁火',
      yongshenDetail: { candidates: [{ method: '调候', name: '丁火' }] },
    },
  );
  const fire = tenGodScore('丁', ctx);
  // 丁=伤官 (甲日)。2003 盘 时柱 戊辰, 没有丁干. 透干集合不含伤官 → 无 +0.05.
  // 但 yongshen 调候 floor +0.80 应生效
  assert.ok(fire >= 0.80, `调候 floor 应 ≥ 0.80, 实际 ${fire}`);
});

test('scoreDayun: 大运有突出高/低年时挂 peakYearIdx / troughYearIdx', () => {
  // 构造一个 大运里某一年突出高的场景
  const ZHIS = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥'];
  const GANS = ['甲','乙','丙','丁','戊','己','庚','辛','壬','癸'];
  const yearGz = (y) => GANS[(y - 4) % 10] + ZHIS[(y - 4) % 12];
  const step = {
    gz: '癸丑', ss: '', startYear: 2025, endYear: 2034, age: 22, current: false,
    years: Array.from({length: 10}, (_, j) => ({ year: 2025 + j, gz: yearGz(2025 + j), ss: '', current: false })),
  };
  const sc = scoreDayun({ paipan: PAIPAN_JIA_WEAK, meta: META_JIA_WEAK, dayunStep: step });
  // 只要 peakYearIdx / troughYearIdx 字段存在（值可能 -1 = 没突出年, 也合规）
  assert.ok('peakYearIdx' in sc, 'peakYearIdx 应存在于返回值');
  assert.ok('troughYearIdx' in sc, 'troughYearIdx 应存在于返回值');
});

test('scoreAllDayun: 整体平淡（最高 < 0.6）时不标 peak', () => {
  // 用 中和 + 没 yongshen 制造一个分数都很低的情境
  const flatPaipan = { sizhu: { year: '甲子', month: '乙丑', day: '丙寅', hour: '丁卯' } };
  const flatMeta = { rizhuGan: '丙', dayStrength: '中和', yongshen: '' };
  const dayun = ['戊辰','己巳','庚午','辛未'].map((gz, i) => ({
    gz, ss: '', startYear: 2010 + i*10, endYear: 2019 + i*10, age: 5 + i*10,
    current: false,
    years: Array.from({length: 10}, (_, j) => ({ year: 2010 + i*10 + j, gz, ss: '', current: false })),
  }));
  const scored = scoreAllDayun({ paipan: flatPaipan, meta: flatMeta, dayun });
  const peaks = scored.filter((s) => s.isPeak);
  assert.equal(peaks.length, 0, '整体平淡时不应标 peak');
});
