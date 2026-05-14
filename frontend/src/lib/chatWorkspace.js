import { buildChartVisibility } from './chartVisibility.js';

function hasValue(value) {
  if (value == null) return false;
  return String(value).trim() !== '';
}

function getOpenDayun(dayun, dayunOpenIdx) {
  if (!Array.isArray(dayun) || dayunOpenIdx == null || dayunOpenIdx < 0) return null;
  return dayun[dayunOpenIdx] || null;
}

function getOpenLiunian(dayun, liunianOpenKey) {
  if (!liunianOpenKey) return null;
  const [dayunIndexRaw, yearIndexRaw] = String(liunianOpenKey).split('-');
  const dayunIndex = Number(dayunIndexRaw);
  const yearIndex = Number(yearIndexRaw);
  if (!Number.isFinite(dayunIndex) || !Number.isFinite(yearIndex)) return null;
  const step = Array.isArray(dayun) ? dayun[dayunIndex] : null;
  const year = step?.years?.[yearIndex] || null;
  if (!step || !year) return null;
  return { step, year };
}

function compact(values) {
  return values.filter((value) => hasValue(value));
}

// 默认空态的 chip：实务（节点）/ 隐喻（一首歌）/ 自察（警觉），各一条。
// label 是 chip 上显示的文本，prompt 是单击后直接 send() 出去的问句。
// 之所以 prompt ≠ label：label 要短到能挤进按钮，prompt 要带"我"的语气
// 让后端 router 识别成命主自问，而不是泛指。
const DEFAULT_OPENING_CHIPS = [
  { label: '接下来两年的关键节点', prompt: '接下来两年我的关键节点在哪里？' },
  { label: '用一首歌形容我', prompt: '用一首歌形容我' },
  { label: '我最该警觉的是什么', prompt: '这盘里我最该警觉的是什么？' },
];

const DAYUN_OPENING_CHIPS = [
  { label: '这十年的主线', prompt: '这步大运这十年的主线是什么？' },
  { label: '这十年最该避开什么', prompt: '这步大运里我最该避开什么？' },
  { label: '大运和原局哪里最冲', prompt: '这步大运和原局最冲的地方在哪里？' },
];

const LIUNIAN_OPENING_CHIPS = [
  { label: '这一年最大的机会', prompt: '这一年我最大的机会是什么？' },
  { label: '这一年最大的压力', prompt: '这一年我最大的压力在哪里？' },
  { label: '用一句话总结这一年', prompt: '用一句话总结这一年' },
];

// AI 开场一句：用盘里已经有的事实（日主 / 格局 / 大运 / 流年）说话，
// 收尾留一个"整体 / 具体"二选一，把决策从 8-way 压到 2-way。
// headline 缺失时退化成只剩 body，但 body 永远存在。
function buildDefaultOpeningLine(visibility, meta) {
  // headline 拼"日主 · 身强弱 · 格局" — visibility.dayMasterText 已经
  // 把日主+身强弱拼好，再补 meta.geju。这是用户首屏看到的第一行 AI 话语，
  // 字段都从盘里直接读，没用神（用神是术语，开场不抛）。
  const fragments = compact([visibility?.dayMasterText, hasValue(meta?.geju) ? meta.geju : null]);
  const headline = fragments.join(' · ');
  return {
    headline: headline || null,
    body: '我先聊整体讲给你听，还是你直接抛一件具体的事？',
  };
}

function buildDayunOpeningLine(dayunFocus) {
  const tag = compact([dayunFocus?.gz ? `${dayunFocus.gz}大运` : null, dayunFocus?.ss]).join(' · ');
  return {
    headline: tag || null,
    body: '我先讲这十年的主线，还是你直接抛一件具体的事？',
  };
}

function buildLiunianOpeningLine(year, step) {
  const tag = compact([year?.year ? `${year.year} ${year.gz || ''}`.trim() : null, year?.ss, step?.gz ? `${step.gz}大运` : null]).join(' · ');
  return {
    headline: tag || null,
    body: '我先讲这一年的总览，还是你直接抛一件具体的事？',
  };
}

export function mergePromptChips(primary = [], secondary = [], max = 4, askedQuestions = []) {
  // askedQuestions: 当前对话里已经发出的用户问题原文。本来 chip 就是
  // "你可能想问"的捷径，已问过的还在显示是浪费 + 误导。这里做一次
  // soft 去重：同字面、或差不多就跳过（短问句很容易完整匹配）。
  const askedNorm = new Set(
    (askedQuestions || [])
      .map((q) => String(q || '').trim())
      .filter(Boolean),
  );
  const seen = new Set();
  const merged = [];
  for (const value of [...primary, ...secondary]) {
    const normalized = String(value || '').trim();
    if (!normalized || seen.has(normalized)) continue;
    if (askedNorm.has(normalized)) continue;
    seen.add(normalized);
    merged.push(normalized);
    if (merged.length >= max) break;
  }
  return merged;
}

export function buildChatWorkspace({
  meta,
  force = [],
  guards = [],
  dayun = [],
  dayunOpenIdx = null,
  liunianOpenKey = null,
} = {}) {
  const visibility = buildChartVisibility({ meta, force, guards });
  const liunianFocus = getOpenLiunian(dayun, liunianOpenKey);
  const dayunFocus = getOpenDayun(dayun, dayunOpenIdx);

  if (liunianFocus) {
    const { step, year } = liunianFocus;
    return {
      title: `${year.year} ${year.gz}`,
      lead: '',
      badges: compact([step?.gz ? `所属 ${step.gz}大运` : null, year?.ss]),
      contextLabel: `${year.year} ${year.gz}`,
      openingLine: buildLiunianOpeningLine(year, step),
      openingChips: LIUNIAN_OPENING_CHIPS,
      starterQuestions: [
        '这一年最大的机会',
        '这一年最大的压力',
        '用一句话总结这一年',
        '这一年怎么取舍',
      ],
    };
  }

  if (dayunFocus) {
    return {
      title: `${dayunFocus.gz}大运`,
      lead: '',
      badges: compact([dayunFocus.age != null ? `${dayunFocus.age}岁起` : null, dayunFocus.ss]),
      contextLabel: `${dayunFocus.gz}大运`,
      openingLine: buildDayunOpeningLine(dayunFocus),
      openingChips: DAYUN_OPENING_CHIPS,
      starterQuestions: [
        '这十年的主线',
        '这十年最该避开什么',
        '用一句话形容这十年',
        '大运和原局哪里最冲',
      ],
    };
  }

  return {
    title: '命盘已经排好了',
    lead: '',
    badges: compact([
      visibility.dayMasterText || null,
      hasValue(meta?.geju) ? meta.geju : null,
      hasValue(meta?.yongshen) ? `用神 ${meta.yongshen}` : null,
    ]),
    contextLabel: null,
    openingLine: buildDefaultOpeningLine(visibility, meta),
    openingChips: DEFAULT_OPENING_CHIPS,
    starterQuestions: [
      '这盘像哪部电影',
      '这盘的核心矛盾',
      '接下来两年的关键节点',
      '我天生擅长什么',
    ],
  };
}
