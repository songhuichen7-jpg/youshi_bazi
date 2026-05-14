// 五行 / 干支 / 喜忌 — 纯查表，给评分引擎用。
//
// 注：与 paipanForce.js 是循环依赖（paipanForce 用本文件的 tenGodOf / GAN_WX /
// CANG_GAN, 我们用 paipanForce 的 analyzePaipanForce / chartForceComboBonus）。
// ES module live binding 保证了 call-time 都已加载, 不会破。
import {
  analyzePaipanForce,
  detectChartVariant,
  chartForceComboBonus,
  chartVariantBonus,
} from './paipanForce.js';

export const GAN_WX = {
  '甲': '木', '乙': '木', '丙': '火', '丁': '火', '戊': '土',
  '己': '土', '庚': '金', '辛': '金', '壬': '水', '癸': '水',
};

export const ZHI_WX = {
  '子': '水', '丑': '土', '寅': '木', '卯': '木', '辰': '土',
  '巳': '火', '午': '火', '未': '土', '申': '金', '酉': '金',
  '戌': '土', '亥': '水',
};

export const GAN_YANG = {
  '甲': true, '乙': false, '丙': true, '丁': false, '戊': true,
  '己': false, '庚': true, '辛': false, '壬': true, '癸': false,
};

// 地支藏干（带权重）— 本气 / 中气 / 余气。
export const CANG_GAN = {
  '子': [{ gan: '癸', weight: 1.0 }],
  '丑': [{ gan: '己', weight: 0.6 }, { gan: '癸', weight: 0.3 }, { gan: '辛', weight: 0.1 }],
  '寅': [{ gan: '甲', weight: 0.7 }, { gan: '丙', weight: 0.2 }, { gan: '戊', weight: 0.1 }],
  '卯': [{ gan: '乙', weight: 1.0 }],
  '辰': [{ gan: '戊', weight: 0.6 }, { gan: '乙', weight: 0.3 }, { gan: '癸', weight: 0.1 }],
  '巳': [{ gan: '丙', weight: 0.7 }, { gan: '戊', weight: 0.2 }, { gan: '庚', weight: 0.1 }],
  '午': [{ gan: '丁', weight: 0.7 }, { gan: '己', weight: 0.3 }],
  '未': [{ gan: '己', weight: 0.6 }, { gan: '丁', weight: 0.3 }, { gan: '乙', weight: 0.1 }],
  '申': [{ gan: '庚', weight: 0.7 }, { gan: '壬', weight: 0.2 }, { gan: '戊', weight: 0.1 }],
  '酉': [{ gan: '辛', weight: 1.0 }],
  '戌': [{ gan: '戊', weight: 0.6 }, { gan: '辛', weight: 0.3 }, { gan: '丁', weight: 0.1 }],
  '亥': [{ gan: '壬', weight: 0.7 }, { gan: '甲', weight: 0.3 }],
};

// 六合表（地支两两相合，化某五行）。巳申合化水（沿用主流派别）。
export const LIU_HE = {
  '子': { partner: '丑', wuxing: '土' },
  '丑': { partner: '子', wuxing: '土' },
  '寅': { partner: '亥', wuxing: '木' },
  '亥': { partner: '寅', wuxing: '木' },
  '卯': { partner: '戌', wuxing: '火' },
  '戌': { partner: '卯', wuxing: '火' },
  '辰': { partner: '酉', wuxing: '金' },
  '酉': { partner: '辰', wuxing: '金' },
  '巳': { partner: '申', wuxing: '水' },
  '申': { partner: '巳', wuxing: '水' },
  '午': { partner: '未', wuxing: '土' },
  '未': { partner: '午', wuxing: '土' },
};

// 六冲：成对（顺序无关）。
export const LIU_CHONG = new Set([
  '子午', '午子', '丑未', '未丑', '寅申', '申寅',
  '卯酉', '酉卯', '辰戌', '戌辰', '巳亥', '亥巳',
]);

// 三合局（齐三化合，缺一为半合）。
export const SAN_HE = [
  { zhi: ['申', '子', '辰'], wuxing: '水' },
  { zhi: ['寅', '午', '戌'], wuxing: '火' },
  { zhi: ['巳', '酉', '丑'], wuxing: '金' },
  { zhi: ['亥', '卯', '未'], wuxing: '木' },
];

// 三刑（不含子卯、自刑，单独处理）
export const SAN_XING = [
  ['寅', '巳', '申'],
  ['丑', '戌', '未'],
];

// 自刑
export const ZI_XING = new Set(['辰', '午', '酉', '亥']);

// 六害（穿）
export const LIU_HAI = {
  '子': '未', '未': '子',
  '丑': '午', '午': '丑',
  '寅': '巳', '巳': '寅',
  '卯': '辰', '辰': '卯',
  '申': '亥', '亥': '申',
  '酉': '戌', '戌': '酉',
};

// 五行相克映射：克 X 的五行是谁（X 的对立元素）
const KE_BY = { '木': '金', '火': '水', '土': '木', '金': '火', '水': '土' };
// 生 X 的五行是谁（X 的母源 — 来生 X）
const SHENG_BY = { '木': '水', '火': '木', '土': '火', '金': '土', '水': '金' };
// X 生 谁（X 的子嗣 — X 来生它）
const SHENG_TO = { '木': '火', '火': '土', '土': '金', '金': '水', '水': '木' };

/**
 * 给一个 五行 element 返回它对 dayMaster 的 十神大类（5 类）。
 *   '比劫' = 同我；'印' = 生我；'食伤' = 我生；'财' = 我克；'官杀' = 克我
 */
export function tenGodCategory(element, dayMasterElement) {
  if (!element || !dayMasterElement) return null;
  if (element === dayMasterElement) return '比劫';
  if (SHENG_BY[dayMasterElement] === element) return '印';
  if (SHENG_TO[dayMasterElement] === element) return '食伤';
  if (KE_BY[dayMasterElement] === element) return '官杀';
  return '财'; // 剩下的就是 日主 克 X
}

/**
 * 给一个**天干**返回它对日主的十神**细分**（10 类）。
 *   同党：比肩 / 劫财（同我）, 正印 / 偏印（生我）
 *   异党：食神 / 伤官（我生）, 正财 / 偏财（我克）, 正官 / 七杀（克我）
 *
 * 阴阳同性 → 偏（偏印/比肩同性 → 实际命学里 比肩 是同性、劫财 异性）。
 * 规则正解：
 *   生我：同性=偏印, 异性=正印
 *   同我：同性=比肩, 异性=劫财
 *   我生：同性=食神, 异性=伤官
 *   我克：同性=偏财, 异性=正财
 *   克我：同性=七杀, 异性=正官
 */
export function tenGodOf(gan, dayMasterGan) {
  if (!gan || !dayMasterGan) return null;
  const a = GAN_WX[dayMasterGan];
  const b = GAN_WX[gan];
  if (!a || !b) return null;
  const samePolarity = GAN_YANG[dayMasterGan] === GAN_YANG[gan];
  if (b === a) return samePolarity ? '比肩' : '劫财';
  if (SHENG_BY[a] === b) return samePolarity ? '偏印' : '正印';
  if (SHENG_TO[a] === b) return samePolarity ? '食神' : '伤官';
  if (KE_BY[a] === b) return samePolarity ? '七杀' : '正官';
  return samePolarity ? '偏财' : '正财'; // 日主 克 X
}

/** 同党 = 印 + 比劫；异党 = 食伤 + 财 + 官杀。 */
export function isSameParty(category) {
  return category === '比劫' || category === '印';
}

/**
 * 十神 → 基础分（取自 GPT 深度研究建议，参《子平真诠》《滴天髓》体系）。
 * 表头：身弱（含极弱前的反转处理） / 中和 / 身强（含极强 + 从弱反转后）。
 *
 * 注意：正印 / 偏印 在基础表里同档；后续 Phase 2 接 用神角色 / 格局 时会再拆。
 */
const TEN_GOD_TABLE = {
  '正印': { weak: 0.85, balanced: 0.10, strong: -0.60 },
  '偏印': { weak: 0.85, balanced: 0.10, strong: -0.60 },
  '比肩': { weak: 0.65, balanced: 0.05, strong: -0.45 },
  '劫财': { weak: 0.50, balanced: 0.00, strong: -0.60 },
  '食神': { weak: -0.35, balanced: 0.05, strong: 0.70 },
  '伤官': { weak: -0.55, balanced: -0.05, strong: 0.55 },
  '正财': { weak: -0.55, balanced: 0.05, strong: 0.65 },
  '偏财': { weak: -0.65, balanced: 0.00, strong: 0.60 },
  '正官': { weak: -0.60, balanced: 0.05, strong: 0.70 },
  '七杀': { weak: -0.80, balanced: -0.10, strong: 0.55 },
};

/** 五行 → 取该五行的阳本气干，给 L2/L4（化合后五行）做 elementScore 用。 */
const ELEMENT_YANG_PROXY = {
  '木': '甲', '火': '丙', '土': '戊', '金': '庚', '水': '壬',
};

/**
 * 把后端 dayStrength 字符串映射成离散信号。
 * 'extreme-weak' / 'weak' / 'balanced' / 'strong' / 'extreme-strong'
 * 顺序很重要 — 先匹配"极/从"，否则会被"弱"先吃掉。
 */
export function classifyDayStrength(dayStrengthStr) {
  const s = String(dayStrengthStr || '');
  if (/极弱|从弱/.test(s)) return 'extreme-weak';
  if (/极强|从强|专旺/.test(s)) return 'extreme-strong';
  if (/弱/.test(s)) return 'weak';
  if (/强|旺/.test(s)) return 'strong';
  return 'balanced';
}

/**
 * 构造评分上下文。score.js 在 scoreYear 入口算一次，下游所有 score 复用。
 *
 * Phase 2 新增：
 *   yongshenRoles  { '火': '调候', '木': '扶抑' } — 从 yongshenDetail.candidates 派生
 *   geju           '七杀格' / '伤官格' / ... — 给 gejuComboBonus 解析用
 */
export function buildScoringContext(paipan, meta) {
  const dayStem = paipan?.sizhu?.day?.[0] || meta?.rizhuGan || '';
  const dayMasterElement = GAN_WX[dayStem] || '';
  const dayStrength = String(meta?.dayStrength || '');
  const yongshenSet = new Set(
    String(meta?.yongshen || '')
      .split('')
      .filter((c) => '木火土金水'.includes(c)),
  );

  // 解析 yongshenDetail.candidates → { element: method } map
  // 例 candidates = [{method:'调候', name:'丁火'}, {method:'扶抑', name:'乙木'}]
  //    → { '火': '调候', '木': '扶抑' }
  const yongshenRoles = {};
  const candidates = meta?.yongshenDetail?.candidates;
  if (Array.isArray(candidates)) {
    for (const c of candidates) {
      const name = String(c?.name || '');
      const method = String(c?.method || '').trim();
      const elem = name.split('').find((ch) => '木火土金水'.includes(ch));
      if (elem && method && !yongshenRoles[elem]) {
        yongshenRoles[elem] = method;
      }
    }
  }

  // Phase 3：命局力量场分析 + 从格变体识别
  // 用 dynamic import 避开循环依赖（paipanForce 反过来 import tenGodOf from this file）
  // — 但因为是同一模块文件、esm 顺序加载, 在文件最后 export 的就行。
  // 实际改成顶部 import (因为 paipanForce 只 import 已声明的 tenGodOf 等)
  const dayStrengthClass = classifyDayStrength(dayStrength);
  const chartForce = paipan ? analyzePaipanForce(paipan, dayStem) : null;
  const chartVariant = chartForce
    ? detectChartVariant(dayStrengthClass, chartForce.patterns, meta?.geju)
    : null;

  return {
    dayMasterGan: dayStem,
    dayMasterElement,
    dayStrength,
    dayStrengthClass,
    yongshenSet,
    yongshenRoles,
    geju: String(meta?.geju || ''),
    hasYongshen: yongshenSet.size > 0,
    chartForce,
    chartVariant,
  };
}

/**
 * 用神角色 → floor。参 GPT 深研 Q4：
 *   病药 +0.85（针对命局"病"，最关键）
 *   调候 / 通关 +0.80（季节失衡 / 两旺通关，覆盖力强）
 *   扶抑 +0.65（普通扶身，主表已经够 — floor 较低，让同党表自然胜出）
 *   未知 / 其它 +0.70（兜底）
 */
function yongshenRoleFloor(method) {
  switch (method) {
    case '病药': return 0.85;
    case '调候': return 0.80;
    case '通关': return 0.80;
    case '扶抑': return 0.65;
    default: return 0.70;
  }
}

/**
 * 格局组合加成 — 按命局 geju + 落到这一柱的十神 做经典组合修正。
 * 参《子平真诠》格局成败救应：食神制杀、杀印相生、伤官见官、伤官配印、
 * 财坏印、枭夺食、比劫夺财、官杀混杂 等。
 *
 * 数值规模偏小（±0.05~±0.20），不抢主表的主导。
 */
function gejuComboBonus(ten, ctx) {
  const geju = ctx.geju || '';
  if (!geju) return 0;

  // 七杀格（含 偏官格 旧名）
  if (/七杀格|偏官格/.test(geju)) {
    if (ten === '食神') return 0.20;   // 食神制杀成格
    if (ten === '伤官') return 0.10;   // 伤官也能制但稍逊
    if (ten === '正印' || ten === '偏印') return 0.15; // 杀印相生
    if (ten === '正官') return -0.10;  // 官杀混杂
    return 0;
  }
  // 正官格
  if (/正官格/.test(geju)) {
    if (ten === '伤官') return -0.20;  // 伤官见官
    if (ten === '七杀') return -0.10;  // 官杀混杂
    if (ten === '正印' || ten === '偏印') return 0.10;
    if (ten === '正财' || ten === '偏财') return 0.10; // 财生官
    return 0;
  }
  // 食神格
  if (/食神格/.test(geju)) {
    if (ten === '偏印') return -0.20;  // 枭夺食
    if (ten === '正财' || ten === '偏财') return 0.10; // 食神生财
    if (ten === '七杀') return 0.05;   // 食神制杀（轻）
    return 0;
  }
  // 伤官格
  if (/伤官格/.test(geju)) {
    if (ten === '正官') return -0.20;  // 伤官见官
    if (ten === '正印' || ten === '偏印') return 0.15; // 伤官配印
    if (ten === '正财' || ten === '偏财') return 0.10; // 伤官生财
    return 0;
  }
  // 财格（正财 / 偏财）
  if (/正财格|偏财格/.test(geju)) {
    if (ten === '比肩' || ten === '劫财') return -0.15; // 比劫夺财
    if (ten === '正官' || ten === '七杀') return 0.10;  // 财生官杀
    if (ten === '食神' || ten === '伤官') return 0.10;  // 食伤生财
    return 0;
  }
  // 印格（正印 / 偏印）
  if (/正印格|偏印格/.test(geju)) {
    if (ten === '正财' || ten === '偏财') return -0.15; // 财坏印
    if (ten === '七杀') return 0.10;   // 杀印相生
    return 0;
  }
  // 建禄格 / 月刃格（阳刃格）
  if (/建禄格|月刃格|阳刃格/.test(geju)) {
    if (ten === '正官' || ten === '七杀') return 0.10; // 比劫需官杀节制
    if (ten === '正财' || ten === '偏财') return 0.08;
    if (ten === '比肩' || ten === '劫财') return -0.05; // 过旺
    return 0;
  }
  return 0;
}

/**
 * 把 dayStrengthClass 映射到查表的 row key。
 *
 * 关键：**极弱（从弱）反转走 strong 行** — 日主从势者，原本异党变喜、同党变忌。
 * 极强 / 专旺 / 从强 维持 strong 行（本身就同党喜，无需反转）。
 */
function tableRowOf(dayStrengthClass) {
  switch (dayStrengthClass) {
    case 'weak': return 'weak';
    case 'extreme-weak': return 'strong'; // 从弱反转
    case 'strong': return 'strong';
    case 'extreme-strong': return 'strong'; // 从强 / 专旺 保持
    case 'balanced':
    default: return 'balanced';
  }
}

/**
 * 给一个**天干** + ctx 返回它的喜忌分。
 *   1. 查 TEN_GOD_TABLE [十神, 日主强弱行]
 *   2. yongshen 命中 (按 element 命中) → 按 用神角色 走差异化 floor
 *      （病药 / 调候 / 通关 / 扶抑 各自 floor 不同）
 *   3. 格局成败救应 — gejuComboBonus 叠加 (例 七杀格 + 食神 → +0.20)
 *
 * 出参范围约 [-1.00, +1.05]，叠加用神 floor 和格局 combo 后边界。
 */
export function tenGodScore(gan, ctx) {
  if (!gan || !ctx || !ctx.dayMasterGan) return 0;
  const ten = tenGodOf(gan, ctx.dayMasterGan);
  if (!ten) return 0;
  const row = tableRowOf(ctx.dayStrengthClass);
  let base = TEN_GOD_TABLE[ten]?.[row] ?? 0;

  // yongshen 角色 floor — Phase 2
  const wx = GAN_WX[gan];
  if (wx && ctx.yongshenSet && ctx.yongshenSet.has(wx)) {
    const role = ctx.yongshenRoles?.[wx];
    base = Math.max(base, yongshenRoleFloor(role));
    // Phase 3：用神透干 / 通根 小 bonus（兜底；命局确实有这个力量）
    const tr = ctx.chartForce?.transparent?.has?.(ten) ? 0.05 : 0;
    const rt = ctx.chartForce?.rooted?.has?.(ten) ? 0.08 : 0;
    base += tr + rt;
  }

  // 格局 combo — Phase 2 (按 meta.geju)
  base += gejuComboBonus(ten, ctx);

  // 命局力量场 combo — Phase 3 (杀重 / 印重 / 比劫多 / 财强 / 食伤多 等场景)
  base += chartForceComboBonus(ten, ctx);

  // 从格变体 — Phase 3 (从财 / 从杀 / 从儿 / 从强)
  base += chartVariantBonus(ten, ctx.chartVariant);

  return base;
}

/**
 * 五行 → 喜忌分（兼容旧接口）。L2/L4 的"化合后五行"没具体干源，用阳本气干代理。
 * 例如 火 → 用 丙 代理评估；土 → 用 戊；水 → 用 壬。
 */
export function elementScore(element, ctx) {
  if (!element || !ctx) return 0;
  const proxyGan = ELEMENT_YANG_PROXY[element];
  if (!proxyGan) return 0;
  return tenGodScore(proxyGan, ctx);
}

// 60 甲子序列（用来算 旬空）。
const GANS = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸'];
const ZHIS = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥'];
const SEXAGENARY = (() => {
  const arr = [];
  // 标准 60 甲子组合：天干循环 10、地支循环 12，最小公倍数 60
  let g = 0, z = 0;
  for (let i = 0; i < 60; i++) {
    arr.push(GANS[g] + ZHIS[z]);
    g = (g + 1) % 10;
    z = (z + 1) % 12;
  }
  return arr;
})();

// 给日柱干支返回该旬的两个空亡支。
export function kongwangZhi(dayGz) {
  const idx = SEXAGENARY.indexOf(dayGz);
  if (idx < 0) return [];
  const xunStart = Math.floor(idx / 10) * 10;
  const usedZhi = new Set();
  for (let i = xunStart; i < xunStart + 10; i++) {
    usedZhi.add(SEXAGENARY[i][1]);
  }
  return ZHIS.filter((z) => !usedZhi.has(z));
}

export { GANS, ZHIS, SEXAGENARY };
