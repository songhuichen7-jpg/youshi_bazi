// 命局力量场分析 — Phase 3。
//
// 给每个十神类型在命局里数 weighted token，识别"杀重""印重""比劫多""财强"
// 这些经典场景。再叠加 用神透干 / 通根 / 从格变体 等结构信号。
// 输出存进 ctx.chartForce 给 tenGodScore 的 chartForceComboBonus 用。
//
// 数据来源：paipan.sizhu 四柱干支 + paipan.cangGan 藏干表。
// 不依赖后端额外字段, 纯前端推导。

import { GAN_WX, CANG_GAN, tenGodOf } from './wuxing.js';

// 月令 (本气) 权重最重 (格局核心); 其它柱天干权重次之; 藏干按本/中/余气递减。
const POSITION_WEIGHTS = {
  yearGan: 0.7,
  monthGan: 1.0,        // 月干 — 透干当令最强
  hourGan: 0.5,
  yearZhiBenqi: 0.4,
  yearZhiMidqi: 0.15,
  yearZhiYuqi: 0.08,
  monthZhiBenqi: 1.2,   // 月支本气 — 格局核心
  monthZhiMidqi: 0.4,
  monthZhiYuqi: 0.15,
  dayZhiBenqi: 0.5,
  dayZhiMidqi: 0.2,
  dayZhiYuqi: 0.08,
  hourZhiBenqi: 0.35,
  hourZhiMidqi: 0.12,
  hourZhiYuqi: 0.06,
};

/**
 * 分析命局力量场。
 *
 * 入参：
 *   paipan.sizhu       { year, month, day, hour } 干支
 *   dayMasterGan       日主天干
 *
 * 返回：
 *   counts             { '正印': 0.7, '比肩': 0.4, ... } 各十神 weighted token sum
 *   transparent        Set<string>  哪些十神有透干（年/月/时干, 不含日干本身）
 *   rooted             Set<string>  哪些十神 同时在干 + 藏干出现（透干通根）
 *   monthGodMain       string|null  月令本气的十神 (格局判定基础)
 *   patterns           {
 *     sevenShaHeavy:    seven杀(含) >= 1.5
 *     yinHeavy:         正印+偏印 >= 1.5
 *     shiShangHeavy:    食神+伤官 >= 1.5
 *     caiHeavy:         正财+偏财 >= 1.5
 *     bijieHeavy:       比肩+劫财 >= 2.0
 *     guanShaMixed:     正官 + 七杀 都有
 *     shiShangMixed:    食神 + 伤官 都有
 *     noControlForSha:  杀重但无印无食伤 (杀无制 — 凶)
 *   }
 */
export function analyzePaipanForce(paipan, dayMasterGan) {
  if (!paipan?.sizhu || !dayMasterGan) {
    return {
      counts: {}, transparent: new Set(), rooted: new Set(),
      monthGodMain: null, patterns: emptyPatterns(),
    };
  }

  const sizhu = paipan.sizhu;
  const yearGan = (sizhu.year || '')[0];
  const yearZhi = (sizhu.year || '')[1];
  const monthGan = (sizhu.month || '')[0];
  const monthZhi = (sizhu.month || '')[1];
  const dayZhi = (sizhu.day || '')[1];
  const hourGan = (sizhu.hour || '')[0];
  const hourZhi = (sizhu.hour || '')[1];

  const counts = {};
  const transparent = new Set();
  // 记录每柱出现过的 干, 用来判断 "通根"（透干 + 藏干都有同一个干）
  const stemSeenInGan = new Set();
  const stemSeenInZhi = new Set();

  function bump(gan, weight, isTransparent) {
    if (!gan) return;
    const ten = tenGodOf(gan, dayMasterGan);
    if (!ten) return;
    counts[ten] = (counts[ten] || 0) + weight;
    if (isTransparent) transparent.add(ten);
  }

  // 天干 (不含日主)
  if (yearGan) { bump(yearGan, POSITION_WEIGHTS.yearGan, true); stemSeenInGan.add(yearGan); }
  if (monthGan) { bump(monthGan, POSITION_WEIGHTS.monthGan, true); stemSeenInGan.add(monthGan); }
  if (hourGan) { bump(hourGan, POSITION_WEIGHTS.hourGan, true); stemSeenInGan.add(hourGan); }

  // 藏干 — 每支按 本/中/余气 三档加权
  function addZhi(zhi, prefix) {
    if (!zhi) return;
    const cg = CANG_GAN[zhi] || [];
    cg.forEach((c, i) => {
      const tier = i === 0 ? 'Benqi' : i === 1 ? 'Midqi' : 'Yuqi';
      const w = POSITION_WEIGHTS[`${prefix}${tier}`] || 0;
      bump(c.gan, w * c.weight, false);
      stemSeenInZhi.add(c.gan);
    });
  }
  addZhi(yearZhi, 'yearZhi');
  addZhi(monthZhi, 'monthZhi');
  addZhi(dayZhi, 'dayZhi');
  addZhi(hourZhi, 'hourZhi');

  // 通根：同一个 干 既透到天干、又作藏干出现 → 这个十神算"通根"
  const rooted = new Set();
  for (const gan of stemSeenInGan) {
    if (stemSeenInZhi.has(gan)) {
      const ten = tenGodOf(gan, dayMasterGan);
      if (ten) rooted.add(ten);
    }
  }

  // 月令本气 → 格局判定基础（虽然后端 meta.geju 已经给, 这里再算一次冗余）
  const monthBenqiGan = (CANG_GAN[monthZhi] || [])[0]?.gan;
  const monthGodMain = monthBenqiGan ? tenGodOf(monthBenqiGan, dayMasterGan) : null;

  // 派生 patterns
  const sevenSha = counts['七杀'] || 0;
  const zhengGuan = counts['正官'] || 0;
  const yinTotal = (counts['正印'] || 0) + (counts['偏印'] || 0);
  const shiShangTotal = (counts['食神'] || 0) + (counts['伤官'] || 0);
  const caiTotal = (counts['正财'] || 0) + (counts['偏财'] || 0);
  const bijieTotal = (counts['比肩'] || 0) + (counts['劫财'] || 0);
  const shiShen = counts['食神'] || 0;
  const shangGuan = counts['伤官'] || 0;

  const patterns = {
    sevenShaHeavy: sevenSha >= 1.5,
    yinHeavy: yinTotal >= 1.5,
    shiShangHeavy: shiShangTotal >= 1.5,
    caiHeavy: caiTotal >= 1.5,
    bijieHeavy: bijieTotal >= 2.0,
    guanShaMixed: sevenSha > 0.3 && zhengGuan > 0.3,
    shiShangMixed: shiShen > 0.3 && shangGuan > 0.3,
    noControlForSha: sevenSha >= 1.5 && yinTotal < 0.5 && shiShangTotal < 0.5,
    // 力量场比例（同党 vs 异党）— 给从格识别用
    sameParty: yinTotal + bijieTotal,
    otherParty: shiShangTotal + caiTotal + sevenSha + zhengGuan,
  };

  return { counts, transparent, rooted, monthGodMain, patterns };
}

function emptyPatterns() {
  return {
    sevenShaHeavy: false, yinHeavy: false, shiShangHeavy: false,
    caiHeavy: false, bijieHeavy: false, guanShaMixed: false,
    shiShangMixed: false, noControlForSha: false,
    sameParty: 0, otherParty: 0,
  };
}

/**
 * 从格变体识别 — 从 dayStrength + 力量场比例 推断 chartVariant。
 *
 * 入参 dayStrengthClass: 'extreme-weak' / 'extreme-strong' / ... (from wuxing.classifyDayStrength)
 * 入参 patterns: from analyzePaipanForce.patterns
 *
 * 返回 chartVariant：
 *   'follow-cai'   从财（从财格）
 *   'follow-sha'   从杀（从杀格）
 *   'follow-er'    从儿（从儿格 / 从食伤）
 *   'follow-weak'  从弱（笼统，无明显主导异党）
 *   'follow-strong' 从强 / 专旺（同党 dominant）
 *   null           普通正格
 *
 * 注意：只在 dayStrengthClass 是 extreme-* 时才识别。中等强弱不强行套 从格。
 */
export function detectChartVariant(dayStrengthClass, patterns, gejuStr) {
  if (!patterns) return null;

  // 优先看 后端 geju 串里的显式信号 — 化气格 / 专旺 / 从X 这些
  // 后端通常会标到 geju 字段里 (如果识别出来)。
  const geju = String(gejuStr || '');
  if (/化气/.test(geju)) return 'transform';     // 甲己化土 / 乙庚化金 等
  if (/专旺|曲直|炎上|稼穑|从革|润下/.test(geju)) return 'dominant';
  // 从财 / 从杀 / 从儿 / 从势 — 如果后端识别出来
  if (/从财/.test(geju)) return 'follow-cai';
  if (/从杀|从官/.test(geju)) return 'follow-sha';
  if (/从儿|从食|从伤/.test(geju)) return 'follow-er';
  if (/从势/.test(geju)) return 'follow-weak';

  // 没有显式 geju 信号 — 退到 dayStrength + patterns 推断
  if (dayStrengthClass === 'extreme-weak') {
    const cai = patterns.caiHeavy;
    const sha = patterns.sevenShaHeavy;
    const er = patterns.shiShangHeavy;
    if (sha && !cai && !er) return 'follow-sha';
    if (cai && !sha && !er) return 'follow-cai';
    if (er && !sha && !cai) return 'follow-er';
    return 'follow-weak';
  }
  if (dayStrengthClass === 'extreme-strong') {
    return 'follow-strong';
  }
  return null;
}

/**
 * 命局力量场 combo bonus — 经典 救应/破格 规则。
 *
 * 输入：
 *   ten: 这个 token 的十神类别（10 类）
 *   ctx: 含 chartForce + yongshenRoles + chartVariant
 *
 * 返回叠加到 base 上的修正值（±0.05 ~ ±0.20）。
 * 不抢 主表 / yongshen floor / gejuComboBonus 的权重。
 */
export function chartForceComboBonus(ten, ctx) {
  const f = ctx?.chartForce;
  if (!f) return 0;
  const p = f.patterns || {};
  let bonus = 0;

  // 杀重 + 印 → 化杀, 印 + 0.15 (杀印相生的实际生效)
  if (p.sevenShaHeavy && (ten === '正印' || ten === '偏印')) {
    bonus += 0.15;
  }
  // 杀重无制（无 印 无 食伤） → 七杀 大忌 -0.20 (整盘的"凶根")
  if (p.noControlForSha && ten === '七杀') {
    bonus -= 0.20;
  }
  // 杀重 + 食伤 → 食伤制杀有功 (七杀格 + 食神 已在 gejuCombo 加了, 这里再轻补)
  if (p.sevenShaHeavy && (ten === '食神' || ten === '伤官')) {
    bonus += 0.05;
  }
  // 印重 + 食伤 → 食伤泄印 (印多需泄)
  if (p.yinHeavy && (ten === '食神' || ten === '伤官')) {
    bonus += 0.10;
  }
  // 印重 + 财 → 财破印 (印多反喜财破)
  if (p.yinHeavy && (ten === '正财' || ten === '偏财')) {
    bonus += 0.08;
  }
  // 财重 + 比劫 → 比劫夺财 (这里是命局已经财多, 流年比劫真的来夺)
  if (p.caiHeavy && (ten === '比肩' || ten === '劫财')) {
    bonus -= 0.10;
  }
  // 比劫多 + 财 → 财被夺, 财来流年是凶
  if (p.bijieHeavy && (ten === '正财' || ten === '偏财')) {
    bonus -= 0.10;
  }
  // 食伤多 + 印 → 印来制食伤 (得印护身)
  if (p.shiShangHeavy && (ten === '正印' || ten === '偏印')) {
    bonus += 0.10;
  }
  // 透干用神 (元素 = yongshen) → 小 bonus +0.05
  // rooted 在 paipanForce 已经算了, 这里只用 transparent 信号
  // 注: caller 把 gan 转到这里, 我们需要再看一下 — 用 yongshenSet 配合
  return bonus;
}

/**
 * 从格变体的额外异党细分 — chartVariant 已识别时, 给"被从的那一类"额外 bonus,
 * 给"破从的对立类"额外 penalty。
 *
 * Phase 1 已经把 extreme-weak 反转到 strong 表 (异党通用变喜), 这里再细化。
 */
export function chartVariantBonus(ten, variant) {
  if (!variant) return 0;
  switch (variant) {
    case 'follow-sha':
      // 从杀：喜七杀 + 财生杀; 忌印 (印护身破从) + 比劫 (帮身破从) + 食伤 (制杀破从)。
      if (ten === '七杀') return 0.20;
      if (ten === '正官') return 0.10;
      if (ten === '正财' || ten === '偏财') return 0.10;
      if (ten === '正印' || ten === '偏印') return -0.30;  // 印破从
      if (ten === '比肩' || ten === '劫财') return -0.25;  // 比劫破从
      if (ten === '食神' || ten === '伤官') return -0.30;  // 食伤制杀破从
      return 0;
    case 'follow-cai':
      // 从财：喜财 + 食伤生财; 忌印破从 + 比劫夺财 + 官杀盗气 (财耗在官杀上)。
      if (ten === '正财' || ten === '偏财') return 0.20;
      if (ten === '食神' || ten === '伤官') return 0.10;
      if (ten === '正印' || ten === '偏印') return -0.30;  // 印破从
      if (ten === '比肩' || ten === '劫财') return -0.25;  // 比劫夺财
      if (ten === '正官' || ten === '七杀') return -0.15;  // 官杀盗财气
      return 0;
    case 'follow-er':
      // 从儿：喜食伤 + 财; 忌印克食伤 + 官杀克身破从。
      if (ten === '食神' || ten === '伤官') return 0.20;
      if (ten === '正财' || ten === '偏财') return 0.10;
      if (ten === '正印' || ten === '偏印') return -0.30;  // 印克食伤破从
      if (ten === '比肩' || ten === '劫财') return -0.10;  // 比劫不旺但也不喜
      if (ten === '正官' || ten === '七杀') return -0.30;
      return 0;
    case 'follow-weak':
      // 笼统从弱：不再细分, 走 extreme-weak 反转表即可
      return 0;
    case 'follow-strong':
      // 从强 / 专旺：同党喜（已 strong 表）; 食伤泄秀亦可
      if (ten === '食神' || ten === '伤官') return 0.10;
      return 0;
    case 'dominant':
      // 专旺格（曲直/炎上/稼穑/从革/润下）— 喜本气 + 生本气, 忌克本气
      // 因为我们这里只拿 十神, 简单按 同党加强、官杀大忌处理
      if (ten === '比肩' || ten === '劫财') return 0.15;
      if (ten === '正印' || ten === '偏印') return 0.10;
      if (ten === '食神' || ten === '伤官') return 0.10;  // 泄秀
      if (ten === '正官' || ten === '七杀') return -0.30; // 克 主元素 大忌
      return 0;
    case 'transform':
      // 化气格 — 化神为主, 化神所生 / 生化神 为辅
      // 简化：喜 同党 + 食伤(泄化神成秀), 忌 强克化神
      if (ten === '比肩' || ten === '劫财') return 0.10;
      if (ten === '正印' || ten === '偏印') return 0.05;
      if (ten === '食神' || ten === '伤官') return 0.08;
      if (ten === '正官' || ten === '七杀') return -0.20; // 破合
      return 0;
    default:
      return 0;
  }
}
