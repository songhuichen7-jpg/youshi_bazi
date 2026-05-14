export function createChatProgress({ contextLabel = null, seed = Date.now(), previousFirst = '' } = {}) {
  return {
    contextLabel,
    phase: 'idle',
    hasOutput: false,
    intent: null,
    intentReason: null,
    // retrievalKinds: 后端 compound retrieval 实际跑了哪些 policy。
    // primary === retrievalKinds[0],其余是 secondary intents。当用户问跨轴
    // 问题(如"讲一下我的整体" → meta + personality)时,UI 显示 "命理概念
    // ＋性格" 类副标签,让用户知道引用的格局/性情两轴材料都来自这次检索。
    retrievalKinds: [],
    needsClassics: null,
    retrievalFocus: [],
    hasRetrieval: false,
    retrievalSources: [],
    modelUsed: null,
    redirectTo: null,
    seed,
    previousFirst,
    // 用于显示"已经等了 N 秒"和超过 12s 的"还在算"友好提示
    startedAt: Date.now(),
  };
}

function parseSources(raw) {
  return String(raw || '')
    .split(/\s*\+\s*/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function applyChatProgressEvent(progress, event) {
  const current = progress || createChatProgress();

  switch (event?.type) {
    case 'intent':
      return {
        ...current,
        phase: 'routing',
        intent: event.intent || null,
        intentReason: event.reason || null,
        retrievalKinds: Array.isArray(event.retrieval_kinds)
          ? event.retrieval_kinds
          : current.retrievalKinds,
        needsClassics: typeof event.needs?.classics === 'boolean'
          ? event.needs.classics
          : (
              typeof event.retrieval_plan?.enabled === 'boolean'
                ? event.retrieval_plan.enabled
                : current.needsClassics
            ),
        retrievalFocus: Array.isArray(event.retrieval_plan?.focus)
          ? event.retrieval_plan.focus
          : current.retrievalFocus,
      };

    case 'retrieval':
      return {
        ...current,
        phase: 'streaming',
        hasRetrieval: true,
        retrievalSources: parseSources(event.source),
      };

    case 'model':
      return {
        ...current,
        phase: current.hasOutput ? current.phase : 'composing',
        modelUsed: event.modelUsed || null,
      };

    case 'delta':
      if (current.hasOutput) return current;
      return {
        ...current,
        hasOutput: true,
        phase: 'streaming',
      };

    case 'redirect':
      return {
        ...current,
        phase: 'redirect',
        redirectTo: event.to || null,
      };

    case 'done':
      return {
        ...current,
        phase: 'done',
      };

    case 'abort':
      return {
        ...current,
        phase: 'stopped',
      };

    default:
      return current;
  }
}

export const INTENT_LABELS = {
  relationship: '感情',
  career: '事业',
  wealth: '财运',
  timing: '时机',
  liunian: '流年',
  dayun_step: '大运',
  personality: '性格',
  health: '身体',
  meta: '命理概念',
  appearance: '外貌',
  special_geju: '特殊格局',
  chitchat: '闲聊',
  divination: '占卜',
  media: '形容比喻',
  other: '综合',
};

export function intentLabel(intent) {
  if (!intent) return '';
  return INTENT_LABELS[intent] || intent;
}

/**
 * 渲染 router 多轴判断成 "主 ＋副1 ＋副2" 形式。
 * 单轴问题 retrievalKinds=[primary] 退化成 intentLabel(primary)。
 * 跨轴问题如 ["meta", "personality"] → "命理概念 ＋性格"。
 *
 * 设计依据:router prompt 给的 secondary_intents 来自 LLM 实际理解,
 * 不是 hardcoded 兜底。前端忠实展示,便于用户理解引文范围跨度。
 */
export function intentLabelWithKinds(primary, retrievalKinds) {
  if (!Array.isArray(retrievalKinds) || retrievalKinds.length === 0) {
    return intentLabel(primary);
  }
  const seen = new Set();
  const ordered = [];
  for (const k of retrievalKinds) {
    if (!seen.has(k)) {
      seen.add(k);
      ordered.push(k);
    }
  }
  // 若 primary 不在列表里也补到首位 (防御性)
  if (primary && !seen.has(primary)) ordered.unshift(primary);
  if (ordered.length <= 1) return intentLabel(ordered[0] || primary);
  const head = intentLabel(ordered[0]);
  const tail = ordered.slice(1).map(intentLabel).join(' ＋');
  return `${head} ＋${tail}`;
}
