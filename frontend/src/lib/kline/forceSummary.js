// 把 paipanForce 的分析结果转成给 LLM 用的**结论文本** + 古籍锚点。
//
// 设计原则：
//   · 只给"结论 / 标签"，不给原始数值（避免 LLM 过度依赖具体数字）
//   · 把关键风险（杀无制 / 财坏印 / 印破从 等）单列一行强调
//   · 关键 pattern 配上经典古籍出处 + 一句原文 — 让 LLM 有具体引文可用
//     (回答里不再"空说理论", 必须按"原文+白话+命盘对应"三段式展开)
//   · 长度控制 — 目标 ~250-350 tokens (加古籍锚点后比之前长, 但可接受)
//
// 输出给 client_context.chart_force, 后端只 wrap 一个 header 后塞进系统提示。

import { analyzePaipanForce, detectChartVariant } from './paipanForce.js';
import { classifyDayStrength } from './wuxing.js';

// 把 token count 转成定性标签
function strengthLabel(value) {
  if (value >= 2.5) return '极重';
  if (value >= 1.5) return '重';
  if (value >= 0.8) return '中';
  if (value >= 0.3) return '弱';
  return '无';
}

function annotateMarks(label, tenGod, force) {
  // 加 透干 / 通根 注脚
  const marks = [];
  if (force.transparent?.has(tenGod)) marks.push('透');
  if (force.rooted?.has(tenGod)) marks.push('根');
  if (marks.length === 0) return label;
  return `${label} (${marks.join('+')})`;
}

const VARIANT_LABEL = {
  'follow-sha': '从杀格',
  'follow-cai': '从财格',
  'follow-er': '从儿格',
  'follow-weak': '从弱格',
  'follow-strong': '从强格',
  'dominant': '专旺格',
  'transform': '化气格',
};

// 关键 pattern → 经典古籍锚点。
// 每条由 { conclusion, source, quote, note } 组成 — 给 LLM 提供具体引文,
// 让"为什么"类问题能"原文 + 白话 + 命盘对应"三段式展开, 不空说理论。
const CLASSICAL_ANCHORS = {
  noControlForSha: {
    conclusion: '杀无制 — 七杀重而印 / 食伤皆无，整盘"凶根"',
    source: '《子平真诠·论七杀》',
    quote: '七杀逢制为佳，无制为忌；非食神制之，即印绶化之。',
    note: '本盘杀重而印 / 食皆无，纯凶之根，必待大运补印化或食制方解。',
  },
  shaYinSheng: {
    conclusion: '杀印相生 — 七杀有印化，凶转为权',
    source: '《滴天髓·七杀》',
    quote: '杀印相生，化煞为权；土衰木盛，众杀横行，一仁可化。',
    note: '行印运为最稳，化杀生身，七杀变贵，最忌财来破印。',
  },
  shiShenZhiSha: {
    conclusion: '食神制杀 — 食神有力，制服七杀成格',
    source: '《子平真诠·食神》',
    quote: '食神制杀，干头透出，月令本气，乃成格之上者。',
    note: '行食伤运是用神到位，最忌印来夺食 (枭神夺食破格)。',
  },
  shangGuanJianGuan: {
    conclusion: '伤官见官 — 伤官格遇正官 / 正官格遇伤官，主败',
    source: '《子平真诠·伤官》',
    quote: '伤官见官，祸患百端；伤官伤尽，反为大贵。',
    note: '本盘已现此结构，行正官 / 伤官大运时压力放大。',
  },
  shangGuanPeiYin: {
    conclusion: '伤官配印 — 伤官旺有印护身，泄而不损',
    source: '《子平真诠·伤官》',
    quote: '伤官佩印，乃成格之要；伤官无印，纵贵亦不久。',
    note: '行印运稳，行财运怕破印。',
  },
  caiYinJiaoZhan: {
    conclusion: '财印交战 — 财旺克印 / 印旺夺财，命局拉锯',
    source: '《滴天髓·财》',
    quote: '财印不可两旺，旺则相战，宜以官杀通其气。',
    note: '走财运易破印，走印运易破财，需官杀通关。',
  },
  guanShaMixed: {
    conclusion: '官杀混杂 — 正官与七杀同现，需取舍清浊',
    source: '《子平真诠·去留舒配》',
    quote: '官煞混杂，宜去煞留官，或去官留煞，不可两存。',
    note: '行食伤合杀 / 财生官 大运时易"清浊分明"，走杀官并见之运反混。',
  },
  followCai: {
    conclusion: '从财格 — 日主极弱，从财之势',
    source: '《滴天髓·从象》',
    quote: '从财者，日主无气，财神得令，全局以财为主。',
    note: '喜食伤生财、官杀泄财；忌印比破从。',
  },
  followSha: {
    conclusion: '从杀格 — 日主极弱，从杀之势',
    source: '《滴天髓·从象》',
    quote: '从杀者，日主孤立无援，七杀当权，弃命相从。',
    note: '喜财生杀；忌印比帮身、食伤制杀破从。',
  },
  followEr: {
    conclusion: '从儿格 — 日主极弱，从食伤之势',
    source: '《滴天髓·从象》',
    quote: '从儿者，从我所生，食伤旺极，日主反弱。',
    note: '喜食伤继续生财；忌印克食伤、官杀克身。',
  },
  dominantPattern: {
    conclusion: '专旺格 — 一行独旺，顺其势',
    source: '《滴天髓·五气偏全》',
    quote: '木旺曲直、火旺炎上、土旺稼穑、金旺从革、水旺润下，顺则发，逆则祸。',
    note: '喜本气 + 顺生 + 泄秀；忌强克本气。',
  },
  transformPattern: {
    conclusion: '化气格 — 日主合化，从所合之神',
    source: '《滴天髓·化象》',
    quote: '化气之神，化之真者，富贵双全；化神受克，则破合不真。',
    note: '喜化神 + 生化神；忌克化神 / 争合 / 破合。',
  },
};

/**
 * 构造给 LLM 用的命局结构分析文本。
 *
 * 入参 paipan / meta — 跟 buildScoringContext 一样。
 * 返回 string（已格式化, 多行）或 null（命盘不足无法分析）。
 */
export function buildChartForceSummary(paipan, meta) {
  if (!paipan?.sizhu || !meta?.rizhuGan) return null;
  const dayMasterGan = meta.rizhuGan;
  const force = analyzePaipanForce(paipan, dayMasterGan);
  const dayStrengthClass = classifyDayStrength(meta.dayStrength);
  const variant = detectChartVariant(dayStrengthClass, force.patterns, meta.geju);

  const dayStrength = String(meta.dayStrength || '').trim() || '?';
  const geju = String(meta.geju || '').trim() || '?';
  const yongshen = String(meta.yongshen || '').trim() || '?';

  // 用神角色 (从 yongshenDetail.candidates 取主用神的 method)
  let yongshenRoleNote = '';
  const candidates = meta?.yongshenDetail?.candidates;
  if (Array.isArray(candidates) && candidates.length > 0) {
    const method = candidates[0]?.method;
    if (method) yongshenRoleNote = ` (${method})`;
  }

  // 力量场 — 把 10 类十神聚成 5 大组 + 标签
  const c = force.counts;
  const groups = [
    { label: '七杀', value: c['七杀'] || 0, ten: '七杀' },
    { label: '正官', value: c['正官'] || 0, ten: '正官' },
    { label: '正印', value: (c['正印'] || 0), ten: '正印' },
    { label: '偏印', value: (c['偏印'] || 0), ten: '偏印' },
    { label: '比肩', value: c['比肩'] || 0, ten: '比肩' },
    { label: '劫财', value: c['劫财'] || 0, ten: '劫财' },
    { label: '食神', value: c['食神'] || 0, ten: '食神' },
    { label: '伤官', value: c['伤官'] || 0, ten: '伤官' },
    { label: '正财', value: c['正财'] || 0, ten: '正财' },
    { label: '偏财', value: c['偏财'] || 0, ten: '偏财' },
  ];

  // 只显示 weight >= 0.3 的项 — 太弱的不输出, 减噪
  const significant = groups.filter((g) => g.value >= 0.3);
  const forceLines = significant
    .map((g) => `  ${annotateMarks(strengthLabel(g.value), g.ten, force)} ${g.label}`)
    .join('\n');

  // 关键判断 + 古籍锚点 — 按命局 patterns + chartVariant + geju 检出适用条目。
  // 每条带《古籍》出处 + 一句原文 + 命盘对应注 — 让 LLM 有可引的具体文字。
  const anchors = [];
  function push(key) {
    const a = CLASSICAL_ANCHORS[key];
    if (a) anchors.push(a);
  }

  if (force.patterns.noControlForSha) push('noControlForSha');
  // 杀印相生：杀重 + 印有 (不能 noControlForSha)
  if (force.patterns.sevenShaHeavy && force.patterns.yinHeavy) push('shaYinSheng');
  // 食神制杀：七杀格 + 命局有食神 (count 食神 > 0.3)
  if (/七杀格|偏官格/.test(geju) && (c['食神'] || 0) >= 0.3) push('shiShenZhiSha');
  // 伤官见官：(伤官格 + 正官 透干 OR 正官格 + 伤官 透干)
  const shangGuanInChart = force.transparent?.has('伤官');
  const zhengGuanInChart = force.transparent?.has('正官');
  if ((/伤官格/.test(geju) && zhengGuanInChart)
      || (/正官格/.test(geju) && shangGuanInChart)) {
    push('shangGuanJianGuan');
  }
  // 伤官配印：伤官格 + 印 (≥ 0.5)
  if (/伤官格/.test(geju) && ((c['正印'] || 0) + (c['偏印'] || 0)) >= 0.5) {
    push('shangGuanPeiYin');
  }
  // 财印交战：财重 + 印重
  if (force.patterns.caiHeavy && force.patterns.yinHeavy) push('caiYinJiaoZhan');
  // 官杀混杂
  if (force.patterns.guanShaMixed) push('guanShaMixed');
  // 从格变体
  if (variant === 'follow-cai') push('followCai');
  if (variant === 'follow-sha') push('followSha');
  if (variant === 'follow-er') push('followEr');
  if (variant === 'dominant') push('dominantPattern');
  if (variant === 'transform') push('transformPattern');

  const lines = [];
  lines.push(`身强弱: ${dayStrength}`);
  lines.push(`格局: ${geju}`);
  lines.push(`用神: ${yongshen}${yongshenRoleNote}`);
  if (forceLines) {
    lines.push('力量场:');
    lines.push(forceLines);
  }
  if (anchors.length > 0) {
    lines.push('');
    lines.push('核心断语（带古籍出处，回答时优先引用其中至少一条）:');
    for (const a of anchors) {
      lines.push(`· ${a.conclusion}`);
      lines.push(`  ${a.source}：「${a.quote}」`);
      lines.push(`  对应本盘：${a.note}`);
    }
  } else if (!variant) {
    lines.push('特殊格局: 无 (按正格 / 扶抑取喜忌)');
  }

  return lines.join('\n');
}
