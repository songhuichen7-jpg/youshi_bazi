export const FORBIDDEN_THINKING_PATTERNS = [
  /正在回复/,
  /请稍候/,
  /客服/,
  /处理中/,
  /loading/i,
];

const GENERAL_LINES = [
  '先把盘面的主线拎出来',
  '看一眼问题落在哪个层次',
  '把原局和当下语境对齐',
  '先不急着下判断',
  '从最有力的结构开始看',
  '把明显的冲突和缓冲分开',
  '让答案离你的问题近一点',
  '先找那条最稳的线索',
  '把命盘当作一张地形图来读',
  '看哪里是势，哪里是选择',
  '从日主、格局和用神之间取线',
  '先把虚的词放下',
  '把能落地的部分挑出来',
  '看这件事是阶段问题还是结构问题',
  '给问题找一个合适的入口',
  '把轻重缓急排一排',
  '先看底色，再看变化',
  '让盘面少一点玄，多一点清楚',
];

const CLASSICS_LINES = [
  '翻一翻古籍旁证',
  '把古书原文和本盘对上',
  '看古籍里哪一句能照到这里',
  '从旁证里取一段有用的光',
  '先让原文说话',
  '把古籍的语气翻成今天能懂的话',
  '看这条判断有没有出处支撑',
  '从古书里挑最贴近的一句',
  '把引文和盘面放在同一张桌上',
  '让旁证帮忙校准答案',
  '看经典文本怎么处理这个结构',
  '从原文里找骨架',
];

const TIMING_LINES = [
  '顺着大运流年的节奏看',
  '先看这几年气候怎么换',
  '把十年一步和一年一节点分开',
  '看变化先从哪里起风',
  '把机会和压力放到同一条时间线上',
  '找这一段时间最该用力的地方',
  '看时机，不把它说成定数',
  '把流年的关键词压短一点',
  '先看大势，再看小节点',
  '把阶段感读清楚',
];

const RELATIONSHIP_LINES = [
  '先看关系里谁在给谁压力',
  '把吸引和消耗分开看',
  '看亲密关系里最容易反复的模式',
  '先不急着说合不合',
  '把需要、表达和边界拆开',
  '看这段关系适合什么节奏',
  '从相处方式而不是标签开始',
  '把关系里的柔处和硬处都看见',
  '看哪里适合靠近，哪里需要留白',
  '先读关系的温度',
];

const CAREER_LINES = [
  '先看能力怎么长出来',
  '把适合做什么和适合怎么做分开',
  '看事业里的主轴和副线',
  '从优势而不是职位名开始',
  '把压力翻译成可用的方向',
  '看这盘更适合冲刺还是深耕',
  '先找长期能复利的能力',
  '看哪里需要舞台，哪里需要土壤',
  '把职业问题放回性格结构里',
  '先看做事的手感',
];

const WEALTH_LINES = [
  '先看财从哪里来',
  '把赚钱方式和花钱节奏分开',
  '看财星是机会还是压力',
  '从资源流动里找答案',
  '先判断财是不是适合快拿',
  '看稳定性和爆发力各占多少',
  '把财运读成经营方式',
  '看哪里适合积累，哪里适合试水',
  '先把风险和欲望分开',
  '看钱背后的能力结构',
];

const CHITCHAT_LINES = [
  '先听你这句话里的意思',
  '把话接住，再慢慢说',
  '先轻一点聊',
  '不急，先把问题放稳',
  '我先顺着你的语气来',
  '这句可以从很近的地方说起',
  '先把答案说得像人话',
  '我们慢慢拆',
  '先回应你真正关心的那一点',
  '不用绕远，直接聊',
];

export const THINKING_COPY_POOLS = {
  general: GENERAL_LINES,
  classics: CLASSICS_LINES,
  timing: TIMING_LINES,
  relationship: RELATIONSHIP_LINES,
  career: CAREER_LINES,
  wealth: WEALTH_LINES,
  chitchat: CHITCHAT_LINES,
};

function pickPool(intent) {
  if (intent === 'chitchat') return THINKING_COPY_POOLS.chitchat;
  if (intent === 'timing' || intent === 'liunian' || intent === 'dayun_step') return THINKING_COPY_POOLS.timing;
  if (intent === 'relationship') return THINKING_COPY_POOLS.relationship;
  if (intent === 'career') return THINKING_COPY_POOLS.career;
  if (intent === 'wealth') return THINKING_COPY_POOLS.wealth;
  return THINKING_COPY_POOLS.general;
}

export function buildThinkingSequence({
  intent = 'other',
  hasClassics = false,
  seed = Date.now(),
  previousFirst = '',
} = {}) {
  const basePool = pickPool(intent);
  const pool = intent === 'chitchat'
    ? basePool
    : (hasClassics ? [...THINKING_COPY_POOLS.classics, ...basePool] : basePool);
  const offset = Math.abs(Number(seed) || 0) % pool.length;
  const lines = [];

  for (let index = 0; lines.length < 3 && index < pool.length * 2; index += 1) {
    const line = pool[(offset + index) % pool.length];
    if (!line || lines.includes(line)) continue;
    if (lines.length === 0 && previousFirst && line === previousFirst) continue;
    lines.push(line);
  }

  return lines;
}
