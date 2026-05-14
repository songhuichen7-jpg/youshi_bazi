// 多盘精准度评估脚本 — 不算单元测试，是给算法跑 6 张代表性命格、
// 对照经典命书读法、打分。运行：
//   node tests/kline-multichart-eval.mjs
//
// 每张盘评估 4 件事:
//   1. 主峰位置：算法挂 isPeak 的大运 vs 经典预期高峰
//   2. 异党 / 同党 大运的相对排序：算法是否反向
//   3. 用神大运是否高分
//   4. 极端忌神大运（如 杀重无制 + 官杀 大运）是否低分
//
// 注：六十甲子大运推法 (顺/逆) 跟年柱 + 性别有关; 这里直接给定预设
// 大运序列以简化测试 (不依赖排盘引擎)。

import { scoreAllDayun } from '../src/lib/kline/score.js';

const ZHIS = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥'];
const GANS = ['甲','乙','丙','丁','戊','己','庚','辛','壬','癸'];
const yearGzOf = (y) => GANS[(y - 4) % 10] + ZHIS[(y - 4) % 12];

function buildDayun(gzs, sy0, age0) {
  return gzs.map((gz, i) => ({
    gz,
    ss: '',
    startYear: sy0 + i * 10,
    endYear: sy0 + i * 10 + 9,
    age: age0 + i * 10,
    current: false,
    years: Array.from({ length: 10 }, (_, j) => ({
      year: sy0 + i * 10 + j,
      gz: yearGzOf(sy0 + i * 10 + j),
      ss: '',
      current: false,
    })),
  }));
}

// ── 6 张代表性命格 ─────────────────────────────────────────────

const CASES = [
  {
    label: '1990 男 辛酉日 身弱 用印+食 (土+水)',
    paipan: { sizhu: { year: '庚午', month: '壬午', day: '辛亥', hour: '乙未' } },
    meta: {
      rizhuGan: '辛', dayStrength: '身弱',
      yongshen: '己土 / 壬水', geju: '正官格',
      yongshenDetail: { candidates: [
        { method: '扶抑', name: '己土' },
        { method: '调候', name: '壬水' },
      ] },
      today: { ymd: '2026-05-11' },
    },
    dayunGzs: ['癸未', '甲申', '乙酉', '丙戌', '丁亥', '戊子', '己丑', '庚寅'],
    startYear: 1997, ageStart: 8,
    classical: {
      summary: '辛金生午月七杀当令, 身弱。喜印化杀 (戊己土) + 食伤调候 (壬癸水)。',
      expected: {
        highRuns: ['戊子', '己丑', '癸未'],   // 印重 + 食伤
        lowRuns: ['丙戌', '丁亥'],             // 官杀回来
        peakNear: ['戊子', '己丑'],            // 老年印峰
      },
    },
  },

  {
    label: '2003 男 甲戌日 身弱用丁火 七杀格 (食神制杀典型)',
    paipan: { sizhu: { year: '癸未', month: '庚申', day: '甲戌', hour: '戊辰' } },
    meta: {
      rizhuGan: '甲', dayStrength: '身弱',
      yongshen: '丁火', geju: '七杀格',
      yongshenDetail: { candidates: [{ method: '调候', name: '丁火' }] },
      today: { ymd: '2026-05-11' },
    },
    dayunGzs: ['己未', '戊午', '丁巳', '丙辰', '乙卯', '甲寅', '癸丑', '壬子'],
    startYear: 2011, ageStart: 8,
    classical: {
      summary: '甲木 申月七杀当令, 庚透。身弱用丁火制杀 + 印水化杀 双高峰。',
      expected: {
        highRuns: ['丁巳', '壬子', '乙卯', '癸丑'],  // 食伤制杀 + 印化杀 + 比劫帮身
        lowRuns: ['己未', '戊午'],                    // 财耗身 + 生杀
        peakNear: ['丁巳', '壬子'],                   // 双高峰
      },
    },
  },

  {
    label: '身强用财官 — 甲日 寅月 比劫旺 用 戊土财',
    paipan: { sizhu: { year: '甲寅', month: '丙寅', day: '甲寅', hour: '甲子' } },
    meta: {
      rizhuGan: '甲', dayStrength: '身强',
      yongshen: '戊土', geju: '建禄格',
      yongshenDetail: { candidates: [{ method: '扶抑', name: '戊土' }] },
      today: { ymd: '2026-05-11' },
    },
    dayunGzs: ['丁卯', '戊辰', '己巳', '庚午', '辛未', '壬申', '癸酉', '甲戌'],
    startYear: 1985, ageStart: 6,
    classical: {
      summary: '甲木 寅月建禄, 比劫极旺。喜财官 (土金) 节制, 忌印比 (水木)。',
      expected: {
        highRuns: ['戊辰', '己巳', '庚午', '辛未'],  // 财官大运
        lowRuns: ['壬申', '癸酉', '甲戌'],            // 印来生身 反不喜
        peakNear: ['戊辰', '庚午'],                   // 财官得力期
      },
    },
  },

  {
    label: '身弱用印 — 丁火日 子月 水官旺 用 木印',
    paipan: { sizhu: { year: '辛酉', month: '庚子', day: '丁卯', hour: '丙午' } },
    meta: {
      rizhuGan: '丁', dayStrength: '身弱',
      yongshen: '乙木', geju: '正官格',
      yongshenDetail: { candidates: [{ method: '通关', name: '乙木' }] },
      today: { ymd: '2026-05-11' },
    },
    dayunGzs: ['己亥', '戊戌', '丁酉', '丙申', '乙未', '甲午', '癸巳', '壬辰'],
    startYear: 1985, ageStart: 7,
    classical: {
      summary: '丁火 子月 正官当令, 水旺克火。身弱用乙木印化官生身, 兼用比劫帮身。',
      expected: {
        highRuns: ['乙未', '甲午'],          // 印 + 比劫
        lowRuns: ['己亥', '癸巳', '壬辰'],   // 财 / 官杀
        peakNear: ['乙未', '甲午'],
      },
    },
  },

  {
    label: '从财格 — 丁火日 极弱 + 财官大旺',
    paipan: { sizhu: { year: '己丑', month: '辛未', day: '丁未', hour: '己酉' } },
    meta: {
      rizhuGan: '丁', dayStrength: '极弱',
      yongshen: '己土',
      geju: '从财格',   // 显式标记
      yongshenDetail: { candidates: [{ method: '格局', name: '己土' }] },
      today: { ymd: '2026-05-11' },
    },
    dayunGzs: ['庚午', '己巳', '戊辰', '丁卯', '丙寅', '乙丑', '甲子', '癸亥'],
    startYear: 1980, ageStart: 5,
    classical: {
      summary: '丁火极弱 + 命局 土金 大旺 (财官当令)。从财格 — 喜财 (土) + 食伤生财 (金), 忌印比 (木火) 破从。',
      expected: {
        highRuns: ['戊辰', '己巳', '庚午'],   // 财官大运 (反主层)
        lowRuns: ['乙丑', '甲子', '癸亥'],    // 印比来则破从
        peakNear: ['戊辰', '己巳'],
      },
    },
  },

  {
    label: '伤官配印 — 庚金日 卯月 伤官旺 用 戊土印',
    paipan: { sizhu: { year: '甲辰', month: '丁卯', day: '庚午', hour: '丙子' } },
    meta: {
      rizhuGan: '庚', dayStrength: '身弱',
      yongshen: '戊土',
      geju: '伤官格',
      yongshenDetail: { candidates: [{ method: '扶抑', name: '戊土' }] },
      today: { ymd: '2026-05-11' },
    },
    dayunGzs: ['戊辰', '己巳', '庚午', '辛未', '壬申', '癸酉', '甲戌', '乙亥'],
    startYear: 1990, ageStart: 6,
    classical: {
      summary: '庚金 卯月 财生官杀煞, 日主弱。用戊土印化伤生身 + 庚辛比劫扶身。',
      expected: {
        highRuns: ['戊辰', '己巳', '庚午', '辛未'],   // 印 + 比劫
        lowRuns: ['壬申', '癸酉', '甲戌', '乙亥'],     // 食伤泄身 + 财
        peakNear: ['戊辰', '庚午'],
      },
    },
  },
];

// ── 评估循环 ────────────────────────────────────────────────────

function evaluate(c) {
  const dayun = buildDayun(c.dayunGzs, c.startYear, c.ageStart);
  const scored = scoreAllDayun({ paipan: c.paipan, meta: c.meta, dayun });
  return scored;
}

function checkExpected(scored, expected) {
  const sorted = [...scored].sort((a, b) => b.score - a.score);
  const top3 = sorted.slice(0, 3).map((s) => s.gz);
  const bottom3 = sorted.slice(-3).map((s) => s.gz);
  const peak = scored.find((s) => s.isPeak);
  const findings = {
    top3,
    bottom3,
    peak: peak?.gz || '(none)',
    matchPeak: peak && expected.peakNear.includes(peak.gz),
    highMatched: expected.highRuns.filter((g) => top3.includes(g)).length,
    lowMatched: expected.lowRuns.filter((g) => bottom3.includes(g)).length,
  };
  return findings;
}

// ── 输出 ───────────────────────────────────────────────────────

let totalCases = 0;
let peakMatches = 0;
let highMatchCount = 0;
let lowMatchCount = 0;

console.log('='.repeat(80));
console.log('K 线评分多盘精准度评估');
console.log('='.repeat(80));

for (const c of CASES) {
  totalCases++;
  console.log('');
  console.log('—'.repeat(80));
  console.log(`【${c.label}】`);
  console.log(`经典: ${c.classical.summary}`);
  const scored = evaluate(c);
  console.log('');
  console.log('  大运评分:');
  for (const s of scored) {
    const expectedHigh = c.classical.expected.highRuns.includes(s.gz);
    const expectedLow = c.classical.expected.lowRuns.includes(s.gz);
    const tag = s.isPeak ? '★PEAK' : (expectedHigh ? '↑' : (expectedLow ? '↓' : '·'));
    const pad = (str, n) => str + ' '.repeat(Math.max(0, n - [...str].reduce((a, c) => a + (c.charCodeAt(0) > 127 ? 2 : 1), 0)));
    console.log(`    ${pad(s.gz, 5)} ${s.score.toFixed(2).padStart(6)} ${s.band.padEnd(14)} ${tag}`);
  }
  const findings = checkExpected(scored, c.classical.expected);
  console.log('');
  console.log(`  top3:    ${findings.top3.join(' / ')}  (经典预期高分: ${c.classical.expected.highRuns.join(' / ')})`);
  console.log(`  bottom3: ${findings.bottom3.join(' / ')}  (经典预期低分: ${c.classical.expected.lowRuns.join(' / ')})`);
  console.log(`  peak:    ${findings.peak}  (经典预期主峰: ${c.classical.expected.peakNear.join(' / ')})`);
  console.log(`  匹配: 主峰=${findings.matchPeak ? '✓' : '✗'}  high命中=${findings.highMatched}/${c.classical.expected.highRuns.length}  low命中=${findings.lowMatched}/${c.classical.expected.lowRuns.length}`);
  if (findings.matchPeak) peakMatches++;
  highMatchCount += findings.highMatched;
  lowMatchCount += findings.lowMatched;
}

console.log('');
console.log('='.repeat(80));
console.log('汇总');
console.log('='.repeat(80));
console.log(`总盘数: ${totalCases}`);
console.log(`主峰位置匹配: ${peakMatches}/${totalCases}`);
console.log(`高分大运 命中: ${highMatchCount}`);
console.log(`低分大运 命中: ${lowMatchCount}`);
