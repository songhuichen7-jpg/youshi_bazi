// 点 K 线 → 注入 chat 的桥。
// 同 React 树同 Zustand store，不走 CustomEvent，直接 store action。
//
// 设计要点：用户气泡里**永远只显示用户改过的问题**，不把结构化卡片塞进
// message 文本里。结构化字段以 `client_context.kline` 一路传到后端，由
// `_render_client_context` 拼到系统提示里 — LLM 拿到，但用户看不到。

import { GAN_WX, ZHI_WX } from './wuxing.js';

const BAND_LABEL = {
  'extreme-high': '极佳',
  'high': '顺',
  'mid': '平',
  'low': '阻',
  'extreme-low': '险',
};

function describeRelations(relations = []) {
  if (relations.length === 0) return '—';
  return relations.map((r) => r.text).join('、');
}

function describeShensha(arr = []) {
  if (arr.length === 0) return '—';
  return arr.join('、');
}

function volatilityLabel(v) {
  if (v >= 0.5) return '大';
  if (v >= 0.2) return '中';
  return '小';
}

/**
 * 流年点击 → 给 chat 的预填 payload。
 *
 * 返回：
 *   {
 *     label,    // chip 显示的短标签
 *     prompt,   // 输入框预填的问题，用户可改
 *     kline,    // 结构化字段，用 client_context.kline 路径传给后端，
 *               // 后端 _render_client_context 渲染成系统提示里的一块
 *   }
 *
 * **不再返回 contextCard markdown** — 那会被塞进 user message，污染气泡。
 */
export function buildLiunianPrefill({ paipan, meta, scored, year, dayunStep, isPast, isCurrent }) {
  if (!scored) return null;
  // current 优先 — 同年既属"过去"也属"当前"时，取"当前"语气
  const phase = isCurrent ? '当前' : isPast ? '过去' : '未来';
  const ganWx = GAN_WX[scored.yearGan] || '';
  const zhiWx = ZHI_WX[scored.yearZhi] || '';
  const dayPillar = paipan?.sizhu?.day || '';
  const yongshen = meta?.yongshen || '';

  const label = `${year.year} ${scored.yearGz}（${phase}流年）`;

  let prompt;
  if (isCurrent) {
    prompt = `${year.year} 是我现在所在的流年，我应该重点抓住什么、避开什么？`;
  } else if (isPast) {
    prompt = `回看 ${year.year} 这一年，按八字的能量我那时候经历的是什么？为什么会是这个走势？`;
  } else {
    prompt = `如果到了 ${year.year}，按这一年的能量盘面，我需要提前为什么做准备？`;
  }

  const kline = {
    scope: 'liunian',
    label,
    phase,
    year: year.year,
    gz: scored.yearGz,
    day_pillar: dayPillar,
    yongshen,
    dayun_gz: dayunStep?.gz || '',
    dayun_shishen: dayunStep?.ss || '',
    year_shishen: scored.yearShishen || '',
    gan_wuxing: `${scored.yearGan}${ganWx}`,
    zhi_wuxing: `${scored.yearZhi}${zhiWx}`,
    relations: describeRelations(scored.relations),
    shensha: describeShensha(scored.shensha),
    band: BAND_LABEL[scored.band] || '',
    score: Number(scored.score.toFixed(2)),
    volatility: volatilityLabel(scored.volatility),
  };

  return { label, prompt, kline };
}

/**
 * 大运点击 → 给 chat 的预填 payload。同上结构。
 */
export function buildDayunPrefill({ paipan, meta, scored, isPast, isCurrent }) {
  if (!scored) return null;
  const phase = isCurrent ? '当前' : isPast ? '过去' : '未来';
  const dayPillar = paipan?.sizhu?.day || '';
  const yongshen = meta?.yongshen || '';

  const label = `${scored.gz} 大运（${scored.startYear}–${scored.endYear} · ${phase}）`;

  let prompt;
  if (isCurrent) {
    prompt = `${scored.gz} 是我现在所在的大运，这十年的主线是什么？我该怎么用这股能量？`;
  } else if (isPast) {
    prompt = `回看 ${scored.gz} 这一步大运（${scored.startYear}–${scored.endYear}），我那十年是被什么主线推动的？`;
  } else {
    prompt = `${scored.gz} 大运（${scored.startYear}–${scored.endYear}）即将到来，主线是什么？我现在能为它做什么准备？`;
  }

  const kline = {
    scope: 'dayun',
    label,
    phase,
    gz: scored.gz,
    shishen: scored.ss || '',
    start_year: scored.startYear,
    end_year: scored.endYear,
    age_start: scored.age,
    day_pillar: dayPillar,
    yongshen,
    band: BAND_LABEL[scored.band] || '',
    score: Number(scored.score.toFixed(2)),
    range: Number(scored.range.toFixed(2)),
    shensha: describeShensha(scored.shensha),
  };

  return { label, prompt, kline };
}
