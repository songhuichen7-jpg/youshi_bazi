// 十神力量 → 人话画像。
//
// 命盘里有十个"神"，每个有一个数值（一般 0–10）。原来的 UI 只有 bar +
// 数字，用户看得懂术语但不知道这分布对自己意味着什么。这个模块负责
// 把 force[] 数组压缩成"一行能被普通人读懂的画像"。
//
// 设计原则：
// - 选出 top 1 / top 2 / 最弱（仅在 val < 1，真正"缺位"时才提）
// - high/low 副本必须是动词或感觉句，不要术语堆术语
// - 完全无数据（空数组 / 全 0）时返回 null，让上游不渲染画像

// 每个十神在"主导"和"缺位"两个极端时的人话注释。
// 同一神的 high 句必须能跟在 "{name}主导 → " 后面读得通；
// low 句必须能跟在 "缺..." 后面读得通。
//
// 这套副本是设计师视角的初稿，专业术士可以替换；结构稳定就行。
const SHISHEN_PORTRAIT = {
  比肩: { high: '同盟感重', low: '缺同盟' },
  劫财: { high: '人际易耗散', low: '人际平淡' },
  食神: { high: '舒展松弛', low: '不爱发声' },
  伤官: { high: '锋芒锐利', low: '收着不外露' },
  正财: { high: '靠脚踏实地', low: '稳收入薄' },
  偏财: { high: '人际财流动', low: '横财少' },
  正官: { high: '在意名分', low: '不被规则管' },
  七杀: { high: '外部压力大', low: '没有人推着走' },
  正印: { high: '有靠山有学识', low: '靠自己' },
  偏印: { high: '思维独特', low: '常规思路' },
};

/** Bar 三色带：缺/平/旺。阈值参照真实命盘观察出来：
 *  - <1：基本"没有"，淡灰（low）
 *  - 1~5：正常人都有的程度，中性（mid）
 *  - >=5：明显偏强，需要点出来（high）
 */
export function classifyForceBand(val) {
  const v = Number(val);
  if (!Number.isFinite(v) || v < 1) return 'low';
  if (v < 5) return 'mid';
  return 'high';
}

function strengthLabel(val) {
  if (val >= 5) return '主导';
  if (val >= 2) return '次之';
  if (val >= 1) return '偏弱';
  return '缺位';
}

export function buildForcePortrait(force) {
  if (!Array.isArray(force) || force.length === 0) return null;
  // 全 0 或缺 val 字段时不渲染画像 — 没有"主导"可言
  const hasAnyValue = force.some((f) => Number(f?.val) > 0);
  if (!hasAnyValue) return null;

  const sorted = [...force].sort((a, b) => (Number(b?.val) || 0) - (Number(a?.val) || 0));
  const top = sorted[0];
  const second = sorted[1];
  const bottom = sorted[sorted.length - 1];

  if (!top || !((Number(top.val) || 0) > 0)) return null;

  const parts = [`${top.name}${strengthLabel(top.val)}`];
  if (
    second
    && (Number(second.val) || 0) > 0
    && (Number(second.val) || 0) < (Number(top.val) || 0)
  ) {
    parts.push(`${second.name}次之`);
  }
  // bottom 仅在确实"缺位"（< 1）时显示，且不能跟 top/second 重复
  const showBottom = bottom
    && bottom.name !== top.name
    && bottom.name !== second?.name
    && (Number(bottom.val) || 0) < 1;
  if (showBottom) {
    parts.push(`${bottom.name}缺位`);
  }

  // reading：主导项的 high 句 + 缺位项的 low 句，逗号连
  const phrases = [];
  const topInterp = SHISHEN_PORTRAIT[top.name];
  if (topInterp?.high) phrases.push(topInterp.high);
  if (showBottom) {
    const bottomInterp = SHISHEN_PORTRAIT[bottom.name];
    if (bottomInterp?.low) phrases.push(bottomInterp.low);
  }

  return {
    headline: parts.join(' · '),
    reading: phrases.length ? phrases.join('、') + '。' : '',
    topName: top.name,
  };
}
