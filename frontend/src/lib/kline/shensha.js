// 5 个核心神煞 — 全部确定性查表，不依赖后端。
// 方法学：以「日支」为查询锚点（个人型神煞，强于年支查法）。
// 天乙贵人 单独查日干。

import { kongwangZhi } from './wuxing.js';

// 桃花：寅午戌见卯，申子辰见酉，巳酉丑见午，亥卯未见子。
const TAOHUA_BY_DAY_ZHI = {
  '寅': '卯', '午': '卯', '戌': '卯',
  '申': '酉', '子': '酉', '辰': '酉',
  '巳': '午', '酉': '午', '丑': '午',
  '亥': '子', '卯': '子', '未': '子',
};

// 华盖：寅午戌见戌（自身），余按三合局取墓库。
const HUAGAI_BY_DAY_ZHI = {
  '寅': '戌', '午': '戌', '戌': '戌',
  '申': '辰', '子': '辰', '辰': '辰',
  '巳': '丑', '酉': '丑', '丑': '丑',
  '亥': '未', '卯': '未', '未': '未',
};

// 将星：三合局之中神。
const JIANGXING_BY_DAY_ZHI = {
  '寅': '午', '午': '午', '戌': '午',
  '申': '子', '子': '子', '辰': '子',
  '巳': '酉', '酉': '酉', '丑': '酉',
  '亥': '卯', '卯': '卯', '未': '卯',
};

// 天乙贵人 — 查日干。
const TIANYI_BY_DAY_GAN = {
  '甲': ['丑', '未'], '戊': ['丑', '未'], '庚': ['丑', '未'],
  '乙': ['子', '申'], '己': ['子', '申'],
  '丙': ['酉', '亥'], '丁': ['酉', '亥'],
  '辛': ['寅', '午'],
  '壬': ['卯', '巳'], '癸': ['卯', '巳'],
};

/**
 * 给定 日柱干支 + 流年支，返回这一年触发的神煞标签数组。
 *
 * 输入：
 *   dayGan: 日干（甲乙丙...）
 *   dayZhi: 日支
 *   dayGz:  日柱完整干支（用来算空亡）
 *   yearZhi: 流年支
 *   yearGz:  流年完整干支（用来算伏吟反吟）
 *   sizhuGz: 命局四柱干支数组 [年柱, 月柱, 日柱, 时柱]
 *
 * 返回：['桃花', '将星', ...]
 */
export function computeShensha({
  dayGan,
  dayZhi,
  dayGz,
  yearZhi,
  yearGz,
  sizhuGz = [],
} = {}) {
  const labels = [];

  if (TAOHUA_BY_DAY_ZHI[dayZhi] === yearZhi) labels.push('桃花');
  if (HUAGAI_BY_DAY_ZHI[dayZhi] === yearZhi) labels.push('华盖');
  if (JIANGXING_BY_DAY_ZHI[dayZhi] === yearZhi) labels.push('将星');

  const tianyiZhis = TIANYI_BY_DAY_GAN[dayGan] || [];
  if (tianyiZhis.includes(yearZhi)) labels.push('天乙贵人');

  if (dayGz) {
    const kong = kongwangZhi(dayGz);
    if (kong.includes(yearZhi)) labels.push('空亡');
  }

  // 伏吟：流年柱与命局任一柱相同。反吟：流年柱天克地冲命局任一柱（简化为 干冲+支冲）。
  if (yearGz) {
    const fuyin = sizhuGz.some((gz) => gz && gz === yearGz);
    if (fuyin) labels.push('伏吟');
  }

  return labels;
}

/**
 * 把神煞标签映射成视觉 marker 字符（不进 y 值，只画在 K 线上）。
 * 单字符 marker — 排版上轻一点，不喧宾夺主。
 */
export const SHENSHA_MARKER = {
  '桃花': '◇',       // 钻石形 — 异性缘 / 桃花
  '华盖': '◌',       // 空心圆 — 清修 / 独处
  '将星': '✦',       // 星 — 贵人 / 权力
  '天乙贵人': '✦',   // 同上
  '空亡': '○',       // 圆 — 虚耗
  '伏吟': '⟳',       // 回旋 — 重复
};

/**
 * 多个神煞同年时的优先级（高优先抢 marker 显示位）。
 */
const PRIORITY = ['将星', '天乙贵人', '桃花', '伏吟', '空亡', '华盖'];

export function pickPrimaryMarker(shenshaArr) {
  if (!shenshaArr || shenshaArr.length === 0) return null;
  for (const p of PRIORITY) {
    if (shenshaArr.includes(p)) return { name: p, glyph: SHENSHA_MARKER[p] };
  }
  return null;
}
