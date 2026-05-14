import { useState, useRef, useEffect, useLayoutEffect } from 'react';
import { useAppStore } from '../store/useAppStore';
import { streamMessage, streamGua } from '../lib/api';
import { finalizeChatTurn, resolveConversationIdForSend } from '../lib/chatFlow';
import GuaCard from './GuaCard';
import { RichText } from './RefChip';
import ErrorState from './ErrorState';
import { friendlyError } from '../lib/errorMessages';
import ConversationSwitcher from './ConversationSwitcher';
import { buildChatWorkspace } from '../lib/chatWorkspace';
import { buildChatClientContext } from '../lib/chatClientContext';
import { applyChatProgressEvent, createChatProgress, intentLabel, intentLabelWithKinds } from '../lib/chatProgress';
import { PROMPT_EXAMPLES, PROMPT_ROTATE_INTERVAL_MS } from '../lib/chatPromptExamples';
import { devLog } from '../lib/devLog';
import { createStreamingTextBuffer } from '../lib/streamingTextBuffer.js';
import { getHepanMineCached } from '../lib/hepanApi.js';
import { AvatarBadge } from './AvatarBadge.jsx';

const LEGACY_NO_RETRIEVAL_INTENTS = new Set(['chitchat', 'media', 'appearance']);

// 从 /api/hepan/mine 同步缓存里查指定 slug 的对子信息，组装 chat 顶 banner
// 与底部 "聚焦" pill 用的 hepanFocus 数据。命中时返回完整对子（带 avatar
// URL，缺图时 AvatarBadge 自己 fallback 到色块），漏 cache 时返回字面回退。
function buildHepanFocus(slug) {
  const cache = getHepanMineCached();
  const item = cache?.items?.find(h => h.slug === slug);
  if (!item) {
    return { slug, a: null, b: null, label: '当前合盘' };
  }
  const aName = item.a_nickname || item.a_cosmic_name || '我';
  const bName = item.b_nickname || item.b_cosmic_name || '对方';
  return {
    slug,
    a: { name: aName, avatarUrl: item.a_avatar_url || null, seed: `${slug}-a` },
    b: { name: bName, avatarUrl: item.b_avatar_url || null, seed: `${slug}-b` },
    label: `${aName} × ${bName}`,
  };
}

/** 思考状态指示器:逐步显示"识别意图 → 翻阅古籍 → 生成回答"三段流水。
 *
 *  - 已完成的步骤用 ✓ 标记 + 淡色文字(不抢主视线)
 *  - 当前 active 步骤用脉动小点 + 主权重
 *  - 是否翻阅古籍由后端 planner 决定，不再按 intent 写死
 *  - 一旦 stream 第一字到达,整个 indicator return null 让回答自己说话
 *
 *  文案选用日常技术性词汇,不写"起笔"这种文艺词 — "正在生成回答…"
 *  比"起笔…"清楚得多。
 *
 */
function ThinkingIndicator({ trace }) {
  const phase = trace?.phase || 'idle';
  const stopped = phase === 'stopped';
  const redirected = phase === 'redirect';
  const intent = trace?.intent || null;
  const sources = Array.isArray(trace?.retrievalSources) ? trace.retrievalSources : [];
  const hasOutput = !!trace?.hasOutput;
  const hasRetrieval = !!trace?.hasRetrieval;

  // 计时 — 当前 active 超过 5s 在右侧附 "· Ns",超过 12s 底部出耐心提示
  const startedAt = trace?.startedAt;
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!startedAt || stopped || hasOutput) return undefined;
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [startedAt, stopped, hasOutput]);
  const now = startedAt ? startedAt + tick * 1000 : 0;
  const elapsedSec = startedAt
    ? Math.max(0, Math.floor((now - startedAt) / 1000))
    : 0;

  // 一旦回答开始流出,整个 indicator 消失 — 不要状态行 + 流式回答双重信号
  if (hasOutput || phase === 'done') {
    return null;
  }

  // ━━ 终态:redirect / stopped 各自一行 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  if (redirected) {
    return (
      <div className="thinking-steps" role="status" aria-live="polite">
        <div className="thinking-step thinking-step-active">
          <span className="thinking-step-marker" aria-hidden="true" />
          <div className="thinking-step-body">
            <div className="thinking-step-label">此问题适合起卦,已为你转入占卜流程</div>
          </div>
        </div>
      </div>
    );
  }
  if (stopped) {
    return (
      <div className="thinking-steps" role="status" aria-live="polite">
        <div className="thinking-step thinking-step-stopped">
          <span className="thinking-step-marker" aria-hidden="true">×</span>
          <div className="thinking-step-body">
            <div className="thinking-step-label">已停止</div>
          </div>
        </div>
      </div>
    );
  }

  // ━━ 三步流水线 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // 后端 planner 会随 intent 事件给出 needs.classics / retrieval_plan.enabled。
  // 老事件没有这个字段时，按旧体验降级：chitchat/media/appearance 跳过古籍。
  const needsClassics = typeof trace?.needsClassics === 'boolean'
    ? trace.needsClassics
    : (intent ? !LEGACY_NO_RETRIEVAL_INTENTS.has(intent) : false);
  const skipRetrieval = intent ? !needsClassics : false;
  const steps = [];

  // Step 1: 识别意图
  // 跨轴问题(router 给了 secondary_intents)用 intentLabelWithKinds 渲染成
  // "命理概念 ＋性格"形式,告诉用户引文范围跨了几轴。单轴问题退化成单一标签。
  const intentDisplay = trace?.retrievalKinds && trace.retrievalKinds.length > 0
    ? intentLabelWithKinds(intent, trace.retrievalKinds)
    : intentLabel(intent);
  steps.push({
    key: 'intent',
    state: intent ? 'done' : 'active',
    label: intent ? `已识别意图  ${intentDisplay}` : '正在识别意图…',
  });

  // Step 2: 翻阅古籍 (仅对需要的 intent 显示)
  if (intent && !skipRetrieval) {
    if (hasRetrieval) {
      const srcText = sources.length > 3
        ? sources.slice(0, 3).join('  ·  ') + `  …等 ${sources.length} 条`
        : sources.join('  ·  ');
      steps.push({
        key: 'retrieval',
        state: 'done',
        label: `翻阅古籍  ${sources.length} 段`,
        detail: srcText,
      });
    } else {
      steps.push({ key: 'retrieval', state: 'active', label: '翻阅古籍中…' });
    }
  }

  // Step 3: 生成回答 (intent 拿到 + 古籍状态明确才显示)
  // 古籍状态明确 = (跳过古籍) OR (已经拿到古籍)。否则不显示 step 3,
  // 让 step 2 的 active 独自承担"现在 AI 在干啥"信号,避免双 active。
  const retrievalSettled = skipRetrieval || hasRetrieval;
  if (intent && retrievalSettled) {
    steps.push({ key: 'compose', state: 'active', label: '正在生成回答…' });
  }

  // 给当前 active step 附上耗时(超过 5s 才挂)
  const stepsWithTime = steps.map((s) => {
    if (s.state !== 'active' || elapsedSec < 5) return s;
    return { ...s, label: `${s.label}  · ${elapsedSec}s` };
  });

  return (
    <div className="thinking-steps" role="status" aria-live="polite">
      {stepsWithTime.map((step) => (
        <div className={`thinking-step thinking-step-${step.state}`} key={step.key}>
          <span className="thinking-step-marker" aria-hidden="true">
            {step.state === 'done' ? '✓' : ''}
          </span>
          <div className="thinking-step-body">
            <div className="thinking-step-label">{step.label}</div>
            {step.detail ? <div className="thinking-step-detail">{step.detail}</div> : null}
          </div>
        </div>
      ))}
      {/* 慢提示由新的 ReasoningPanel 取代（"推演中 · X 秒"自带计时），
        * 这里不再额外贴一行"还在思考…"，避免视觉重复。 */}
    </div>
  );
}

function CtaBubble({ question, manual, onCast, onAnalyze, disabled }) {
  const [q, setQ] = useState(question || '');
  const castTarget = manual || !question ? q : question;
  return (
    <div className="cta-bubble">
      {!manual && question && (
        <div style={{ marginBottom: 8, fontSize: 13, color: '#555' }}>
          这个问题适合起一卦，要不要为你算一下？
        </div>
      )}
      {(manual || !question) && (
        <input
          value={q}
          onChange={e => setQ(e.target.value)}
          onKeyDown={e => {
            // IME 合成中（中文输入法选词）的 Enter 不能触发发送
            if (e.key === 'Enter' && !e.nativeEvent.isComposing && e.keyCode !== 229) onCast(q);
          }}
          placeholder="问一件具体的事，例如：下周该不该换工作"
          disabled={disabled}
          style={{
            width: '100%', padding: '6px 10px', fontSize: 13,
            border: '1px solid #ccc', marginBottom: 8, boxSizing: 'border-box',
          }}
        />
      )}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button
          className="btn-primary"
          onClick={() => onCast(castTarget)}
          disabled={disabled || !castTarget?.trim()}
          style={{ fontSize: 12, padding: '4px 14px' }}
        >
          {disabled ? '占算中…' : '起一卦'}
        </button>
        {!manual && question && onAnalyze && (
          <button
            onClick={() => onAnalyze(question)}
            disabled={disabled}
            style={{
              fontSize: 12, padding: '4px 14px', background: 'none',
              border: '1px solid #bbb', cursor: 'pointer', color: '#555',
            }}
          >
            用命盘直接分析
          </button>
        )}
      </div>
    </div>
  );
}

function isAbortError(error) {
  if (!error) return false;
  return error.name === 'AbortError' || /aborted|abort/i.test(String(error.message || error));
}

// ── 消息操作图标 ─────────────────────────────────────────────────────
// 跟 Claude 客户端一个语言：操作不写文字，用 14px 内联 SVG，hover 才显形。
// 全部画成 stroke="currentColor" 让父元素 color 控色，不依赖外部图标库。
const _ICONS = {
  copy: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <rect x="5" y="5" width="9" height="9" rx="1.2" />
      <path d="M11 5V3.5A1.5 1.5 0 0 0 9.5 2H3.5A1.5 1.5 0 0 0 2 3.5v6A1.5 1.5 0 0 0 3.5 11H5" />
    </svg>
  ),
  check: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 8.5l3.2 3 6.8-7" />
    </svg>
  ),
  edit: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 2.5l2.5 2.5L5.8 12.7l-3.2.7.7-3.2z" />
      <path d="M10 3.5l2.5 2.5" />
    </svg>
  ),
  refresh: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9" />
      <path d="M13.5 2.5v3h-3" />
    </svg>
  ),
  stop: (
    <svg viewBox="0 0 16 16" fill="currentColor">
      <rect x="4" y="4" width="8" height="8" rx="1" />
    </svg>
  ),
};

function IconButton({ icon, label, onClick, disabled, danger }) {
  return (
    <button
      type="button"
      className={'msg-action-btn' + (danger ? ' msg-action-btn-danger' : '')}
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
    >
      {_ICONS[icon]}
    </button>
  );
}

// 相对时间 — "刚刚 / 5 分钟前 / 2 天前 / 04.30"。给消息行 hover 时露的时间戳
// 用，跟 hepan 历史的 _relativeTime 同款实现，重复一份避免跨模块依赖。
function _relativeTime(ts) {
  if (!ts) return '';
  const t = typeof ts === 'number' ? ts : Date.parse(ts);
  if (!Number.isFinite(t)) return '';
  const diff = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (diff < 30) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff / 60) || 1} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} 天前`;
  const d = new Date(t);
  return `${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
}

// 复制文本到剪贴板，带 fallback。返回 boolean 给调用方决定要不要 toast。
async function _copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // http / 私密模式 / 无 focus → fallback 到老的 textarea + execCommand
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(ta);
      return ok;
    } catch { return false; }
  }
}

function findPreviousUserIndex(history, index) {
  for (let i = index - 1; i >= 0; i -= 1) {
    if (history[i]?.role === 'user') return i;
  }
  return -1;
}

function settleFollowToBottom(el) {
  if (!el) return;
  const snap = () => {
    el.scrollTop = el.scrollHeight;
  };
  const raf = typeof requestAnimationFrame === 'function'
    ? requestAnimationFrame
    : (cb) => setTimeout(cb, 0);
  snap();
  raf(() => {
    snap();
    raf(snap);
  });
}

export default function Chat() {
  const history = useAppStore(s => s.chatHistory);
  const pushChat = useAppStore(s => s.pushChat);
  const replaceLastAssistant = useAppStore(s => s.replaceLastAssistant);
  const prepareChatRegeneration = useAppStore(s => s.prepareChatRegeneration);
  const replacePlaceholderWithCta = useAppStore(s => s.replacePlaceholderWithCta);
  const replaceLastCtaWithAssistant = useAppStore(s => s.replaceLastCtaWithAssistant);
  const pushGuaCard = useAppStore(s => s.pushGuaCard);
  const updateLastGuaCard = useAppStore(s => s.updateLastGuaCard);
  const llmEnabled = useAppStore(s => s.llmEnabled);
  const chatStreaming = useAppStore(s => s.chatStreaming);
  const setChatStreaming = useAppStore(s => s.setChatStreaming);
  const guaStreaming = useAppStore(s => s.guaStreaming);
  const setGuaStreaming = useAppStore(s => s.setGuaStreaming);
  const setGuaCurrent = useAppStore(s => s.setGuaCurrent);
  const bumpQuotaUsage = useAppStore(s => s.bumpQuotaUsage);
  const setAppNotice = useAppStore(s => s.setAppNotice);
  const view = useAppStore(s => s.view);
  const meta = useAppStore(s => s.meta);
  const paipan = useAppStore(s => s.paipan);
  const force = useAppStore(s => s.force);
  const guards = useAppStore(s => s.guards);
  const dayun = useAppStore(s => s.dayun);
  const dayunOpenIdx = useAppStore(s => s.dayunOpenIdx);
  const liunianOpenKey = useAppStore(s => s.liunianOpenKey);
  const setDayunOpenIdx = useAppStore(s => s.setDayunOpenIdx);
  const setLiunianOpenKey = useAppStore(s => s.setLiunianOpenKey);
  const classics = useAppStore(s => s.classics);
  const currentConversationId = useAppStore(s => s.currentConversationId);
  const conversations = useAppStore(s => s.conversations);
  const ensureConversation = useAppStore(s => s.ensureConversation);
  const newConversationOnServer = useAppStore(s => s.newConversationOnServer);
  const chatPrefill = useAppStore(s => s.chatPrefill);
  const clearChatPrefill = useAppStore(s => s.clearChatPrefill);
  // Chat history pagination
  const chatHistoryHasMore = useAppStore(s => s.chatHistoryHasMore);
  const chatHistoryLoadingOlder = useAppStore(s => s.chatHistoryLoadingOlder);
  const fetchOlderChatMessages = useAppStore(s => s.fetchOlderChatMessages);

  const [input, setInput] = useState('');
  const [chatError, setChatError] = useState(null);
  const [chatTrace, setChatTrace] = useState(null);
  const [editingUserIndex, setEditingUserIndex] = useState(null);
  const [editingText, setEditingText] = useState('');
  // 复制按钮的"已复制"反馈用 Map 记一下哪条消息刚复制了 — 用 message
  // index 当 key，1.4 秒后清掉。同时点多条互不影响（虽然概率低）。
  const [copiedKey, setCopiedKey] = useState(null);
  // Rotating placeholder example: random first index per session, advance
  // every PROMPT_ROTATE_INTERVAL_MS while the input is empty + idle + not focused.
  const [exampleIdx, setExampleIdx] = useState(
    () => Math.floor(Math.random() * PROMPT_EXAMPLES.length),
  );
  // 已经在本会话里展示过的 placeholder 索引；同一会话内不让同一条重复出现，
  // 直到全部走过一遍再 reset（保留当前那条不立即重出）。
  const shownExampleIdxRef = useRef(new Set());
  // 输入框 focus 中暂停轮播 — 用户停留在输入框上时八成在读 / 想措辞，
  // 字符底下一直翻反而像在催。focus 解除后再恢复。
  const [inputFocused, setInputFocused] = useState(false);
  // 空态进入时的"正在读这张盘…"800ms 入场 — 让右栏不再"啪"地一下就把
  // headline + chip 全塞过来；先有一拍 AI 在看盘的呼吸，再 fade 进开场。
  // 每个 conversation 只播一次（切到旧对话再切回来不重播）。Hepan 空态
  // 不走这条路径，它的"试试问" CTA 已经自带启动感。
  const [chartReading, setChartReading] = useState(false);
  const readingShownConvRef = useRef(new Set());
  const bodyRef = useRef(null);
  const inputRef = useRef(null);
  const streamAbortRef = useRef(null);
  const assistantDeltaBufferRef = useRef(null);
  // K 线点 candle 注入的"一次性上下文" — 用户气泡始终只显示用户改过的问题
  // （干净）。结构化字段（评分 / 关系 / 神煞 / 流年大运 etc.）通过 client_context.kline
  // 一路传给后端，由 _render_client_context 拼到系统提示里。LLM 拿到，用户看不到。
  // 发完 / 关闭 chip / 切对话都会清空。
  const klineContextRef = useRef(null);
  const [klineContextLabel, setKlineContextLabel] = useState(null);

  // 模型思考过程（DeepSeek R1 / MiMo 系的 reasoning_content 流）。
  // 不持久 — 只在当前 stream 显示。流式时自动展开，第一个答案 token 到时
  // 自动收起，用户后续可点开再看。切对话清空。
  const [thinking, setThinking] = useState({
    text: '', streaming: false, expanded: true, startedAt: 0, endedAt: 0,
  });
  // 该 stream 是否已经收到过第一个答案 token — 用来控制只 auto-collapse 一次。
  const thinkingFirstContentRef = useRef(false);

  function resetThinkingForNewStream() {
    thinkingFirstContentRef.current = false;
    setThinking({ text: '', streaming: true, expanded: true, startedAt: Date.now(), endedAt: 0 });
  }

  function appendThinkingDelta(running) {
    setThinking((prev) => ({
      ...prev,
      text: running,
      streaming: true,
      // 已经 auto-collapsed 之后，再来的 thinking delta 不重新展开 — 用户视
      // 觉里答案才是主角；想看完整推演自己点开。
      expanded: thinkingFirstContentRef.current ? prev.expanded : true,
    }));
  }

  function endThinkingStream() {
    setThinking((prev) => ({
      ...prev,
      streaming: false,
      endedAt: prev.endedAt || Date.now(),
    }));
  }

  function toggleThinkingExpanded() {
    setThinking((prev) => ({ ...prev, expanded: !prev.expanded }));
  }
  // 每个对话保留各自的输入草稿。在 A 输了一半切到 B，再切回 A，
  // 应该能看到原文还在；不会"打了一半的内容突然没了"。
  const inputDraftRef = useRef(new Map());

  // 滚动管理：
  //   - stuckToBottom: 用户当前是否"贴在底部"。流式 delta 只在贴底时跟随，
  //     否则保留用户的位置，避免阅读上文时被新内容拽走。
  //   - showJumpToBottom: 离底超过阈值时显示一个 ↓ 浮动按钮，点了立刻吸底。
  //   - scrollMemoryRef: { convId → {top, stuck} } 切换对话时把上一会话的
  //     滚动位置存住、新会话进入时按记忆恢复，否则默认贴底。
  const scrollMemoryRef = useRef(new Map());
  const prevConvIdRef = useRef(currentConversationId);
  const shouldForceFollowRef = useRef(false);
  const [stuckToBottom, setStuckToBottom] = useState(true);
  const [showJumpToBottom, setShowJumpToBottom] = useState(false);
  // 分页加载老消息时用：fetchOlder 之前记下当前 scrollHeight + scrollTop，
  // history prepend 触发 re-render 后，useLayoutEffect 在 idChanged 检查
  // 之前先消费这个 anchor 把 scrollTop 调到"用户原本看的那条消息"对应的
  // 新位置（newHeight - oldHeight + oldScrollTop）。这样用户视图锚定不
  // 跳动，老消息只是从顶部 prepend 进来。
  const pendingScrollAnchorRef = useRef(null);
  const olderSentinelRef = useRef(null);

  if (!assistantDeltaBufferRef.current) {
    assistantDeltaBufferRef.current = createStreamingTextBuffer();
  }

  const workspace = buildChatWorkspace({
    meta,
    force,
    guards,
    dayun,
    dayunOpenIdx,
    liunianOpenKey,
  });
  const currentConversation = (conversations || []).find(c => c.id === currentConversationId) || null;
  // hepan-bound 对话的聚焦标签必须始终是 `A × B`，即便 conversation.label
  // 是用户自起的"对话 N"也不能盖掉 — 这是 chat 顶 banner 的语义，不是
  // ConversationSwitcher 下拉的语义。所以这里不走 getConversationDisplayLabel
  // 的 explicit-label 优先级，直接读 hepanMine cache 拿对子的 nickname
  // / cosmic_name + avatar，缺则回退到 "当前合盘"。
  const hepanFocus = currentConversation?.hepan_slug
    ? buildHepanFocus(currentConversation.hepan_slug)
    : null;
  const activeContextLabel = hepanFocus?.label || workspace.contextLabel;
  const clientContext = buildChatClientContext({ view, workspace, classics, paipan, meta });

  function clearActiveContext() {
    if (liunianOpenKey) setLiunianOpenKey(null);
    if (dayunOpenIdx != null) setDayunOpenIdx(null);
  }

  function clearKlineContext() {
    klineContextRef.current = null;
    setKlineContextLabel(null);
  }

  // K 线点击 → 一次性 prefill。把问题装进输入框，把结构化 kline 字段暂存
  // 在 ref 里 — 后面 send 时挂在 client_context.kline 上发给后端，**不进**
  // user message 文本，所以用户气泡始终只显示干净的问题。
  useEffect(() => {
    if (!chatPrefill) return;
    const promptText = chatPrefill.prompt || '';
    const kline = chatPrefill.kline || null;
    const label = chatPrefill.label || '已加入上下文';
    setInput(promptText);
    klineContextRef.current = kline;
    setKlineContextLabel(label);
    clearChatPrefill();
    // focus + caret 移到末尾，让用户回车直接发，或微改前置词
    requestAnimationFrame(() => {
      const el = inputRef.current;
      if (!el) return;
      el.focus();
      const len = promptText.length;
      try { el.setSelectionRange(len, len); } catch { /* ignore */ }
    });
  }, [chatPrefill, clearChatPrefill]);

  // 切对话 / 关闭 chip 时把 K 线 context 一起清掉，避免错位带到下一个问题。
  useEffect(() => {
    clearKlineContext();
    // 切对话时把当前 stream 残留的 thinking panel 也清掉，否则旧对话的推演
    // 内容会跟着新对话留在屏上。
    setThinking({ text: '', streaming: false, expanded: true, startedAt: 0, endedAt: 0 });
    thinkingFirstContentRef.current = false;
    /* eslint-disable-next-line */
  }, [currentConversationId]);
  function distanceFromBottom(el) {
    return el.scrollHeight - el.scrollTop - el.clientHeight;
  }

  function onChatScroll() {
    const el = bodyRef.current;
    if (!el) return;
    const dist = distanceFromBottom(el);
    const stuck = dist < 12;
    setStuckToBottom(stuck);
    setShowJumpToBottom(dist > 120);
    if (currentConversationId) {
      scrollMemoryRef.current.set(currentConversationId, { top: el.scrollTop, stuck });
    }
  }

  function jumpToBottom() {
    const el = bodyRef.current;
    if (!el) return;
    settleFollowToBottom(el);
    setStuckToBottom(true);
    setShowJumpToBottom(false);
    if (currentConversationId) {
      scrollMemoryRef.current.set(currentConversationId, { top: el.scrollHeight, stuck: true });
    }
  }

  function forceFollowNextRender() {
    shouldForceFollowRef.current = true;
    setStuckToBottom(true);
    setShowJumpToBottom(false);
    settleFollowToBottom(bodyRef.current);
  }

  function applyAssistantDelta(running) {
    replaceLastAssistant(running);
    forceFollowNextRender();
    updateTrace({ type: 'delta' });
    // 第一个答案 token 到 → 把思考面板自动折叠（只触发一次；用户已手动展
    // 开过的话也尊重一次性自动收起 — 收完之后他可以再点开看）。
    if (!thinkingFirstContentRef.current) {
      thinkingFirstContentRef.current = true;
      setThinking((prev) => (prev.text ? { ...prev, expanded: false } : prev));
    }
  }

  function scheduleAssistantDelta(running) {
    assistantDeltaBufferRef.current.setOnFlush(applyAssistantDelta);
    assistantDeltaBufferRef.current.push(running);
  }

  function flushAssistantDelta() {
    assistantDeltaBufferRef.current.setOnFlush(applyAssistantDelta);
    assistantDeltaBufferRef.current.flush();
  }

  // 一个 layout effect 同时处理"切对话恢复"和"流式跟随"。在 paint 前完成
  // scrollTop / 输入框草稿 的写入，避免 jitter。
  useLayoutEffect(() => {
    const el = bodyRef.current;
    if (!el) return;
    // 优先消费 prepend-older 的 scroll anchor：history 被 prepend 老消息后，
    // 把 scrollTop 调到用户原本看的位置（newHeight - oldHeight + oldScrollTop）
    // 避免视图跳到新加的最顶部。这条路径走完直接 return，不进 idChanged /
    // stuckToBottom / forceFollow 的常规分支。
    const anchor = pendingScrollAnchorRef.current;
    if (anchor) {
      pendingScrollAnchorRef.current = null;
      const newHeight = el.scrollHeight;
      el.scrollTop = anchor.oldScrollTop + (newHeight - anchor.oldHeight);
      return;
    }
    const prevId = prevConvIdRef.current;
    const idChanged = prevId !== currentConversationId;
    if (idChanged) {
      // 1. 把旧对话的输入草稿存起来（空字符串则删除条目，避免 Map 膨胀）
      if (prevId) {
        if (input && input.trim()) inputDraftRef.current.set(prevId, input);
        else inputDraftRef.current.delete(prevId);
      }
      // 2. 切到新对话时还原草稿（没有就清空）
      const incomingDraft = currentConversationId
        ? (inputDraftRef.current.get(currentConversationId) || '')
        : '';
      setInput(incomingDraft);
      // 3. 滚动位置恢复
      prevConvIdRef.current = currentConversationId;
      const mem = currentConversationId
        ? scrollMemoryRef.current.get(currentConversationId)
        : null;
      if (mem) {
        el.scrollTop = mem.top;
        setStuckToBottom(mem.stuck);
      } else {
        settleFollowToBottom(el);
        setStuckToBottom(true);
      }
      setShowJumpToBottom(distanceFromBottom(el) > 120);
      return;
    }
    if (shouldForceFollowRef.current || stuckToBottom) {
      shouldForceFollowRef.current = false;
      settleFollowToBottom(el);
      setShowJumpToBottom(false);
      if (currentConversationId) {
        scrollMemoryRef.current.set(currentConversationId, { top: el.scrollHeight, stuck: true });
      }
    } else {
      // 不在底部时，新内容来了 → 提示用户"下面有新内容"
      if (distanceFromBottom(el) > 120) setShowJumpToBottom(true);
    }
  }, [history, currentConversationId, stuckToBottom, input, chatStreaming, guaStreaming]);

  useEffect(() => {
    if (!inputRef.current) return;
    inputRef.current.style.height = '0px';
    // 240px ≈ 10 行 14px 字号文本。之前 140px 写长追问只能看到 5-6 行内部
    // 滚动，跟其他 AI 输入框比偏小；放到 240px 跟 ChatGPT/Claude 一档，超
    // 过仍内部滚动避免占满屏幕。
    inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 240)}px`;
  }, [input]);

  // P7 分页加载：用 IntersectionObserver 监听 chat-body 顶部的 sentinel
  // 进入视野时拉上一页老消息（最多 50 条）。fetchOlder 前记下 scrollHeight/
  // scrollTop 进 pendingScrollAnchorRef，useLayoutEffect 在 prepend 完成后
  // 用 anchor 把视图锚定回用户原本看的内容。
  useEffect(() => {
    if (!chatHistoryHasMore) return undefined;
    const sentinel = olderSentinelRef.current;
    const root = bodyRef.current;
    if (!sentinel || !root) return undefined;
    const obs = new IntersectionObserver(async ([entry]) => {
      if (!entry.isIntersecting) return;
      // 防并发：store 内部也有 loadingOlder guard，但 observer 可能在状态
      // 同步前连发，这里再 check 一次。
      const s = useAppStore.getState();
      if (s.chatHistoryLoadingOlder || !s.chatHistoryHasMore) return;
      pendingScrollAnchorRef.current = {
        oldHeight: root.scrollHeight,
        oldScrollTop: root.scrollTop,
      };
      await fetchOlderChatMessages();
    }, { root, rootMargin: '50px' });
    obs.observe(sentinel);
    return () => obs.disconnect();
  }, [chatHistoryHasMore, currentConversationId, fetchOlderChatMessages]);

  // 切换对话时的清理：原版只是把 ref 置 null，留了 4 个真问题：
  //   1. 没真正 abort 在飞的 stream — onDelta 继续 fire，写到新对话的
  //      末尾 assistant 占位符 → 用户在新对话里看到旧对话的乱码
  //   2. ref 被置空后再点"停止"是 no-op，UI 死按钮直到 stream 自然结束
  //   3. editingUserIndex 没清 → 切到新对话还停在编辑态，index 错位
  //   4. chatError 没清 → 切到无错的新对话还显示错误条
  // 切对话就是个明确的"扔掉这一轮"信号，全套清理掉。
  useEffect(() => {
    setChatTrace(null);
    setChatError(null);
    setEditingUserIndex(null);
    setEditingText('');
    if (streamAbortRef.current) {
      try { streamAbortRef.current.abort(); } catch { /* AbortController.abort 不抛 */ }
      streamAbortRef.current = null;
    }
    assistantDeltaBufferRef.current?.cancel();
  }, [currentConversationId]);

  useEffect(() => () => {
    assistantDeltaBufferRef.current?.cancel();
  }, []);

  async function ensureConversationId() {
    const state = useAppStore.getState();
    return resolveConversationIdForSend({
      currentConversationId: state.currentConversationId,
      currentChartId: state.currentId,
      ensureConversation,
    });
  }

  function beginTrace() {
    setChatTrace(createChatProgress({ contextLabel: workspace.contextLabel, seed: Date.now() }));
  }

  function updateTrace(event) {
    setChatTrace((current) => applyChatProgressEvent(current, event));
  }

  function bindStreamController() {
    const controller = new AbortController();
    streamAbortRef.current = controller;
    return controller;
  }

  function releaseStreamController(controller) {
    if (streamAbortRef.current === controller) {
      streamAbortRef.current = null;
    }
  }

  function stopStreaming() {
    if (!streamAbortRef.current) return;
    streamAbortRef.current.abort();
    updateTrace({ type: 'abort' });
  }

  function beginEditUserMessage(index, content) {
    if (chatStreaming || guaStreaming) return;
    setChatError(null);
    setEditingUserIndex(index);
    setEditingText(String(content || ''));
  }

  function cancelEditUserMessage() {
    setEditingUserIndex(null);
    setEditingText('');
  }

  async function regenerateFromUser(index, content) {
    const q = String(content || '').trim();
    if (!q || chatStreaming || guaStreaming) return;
    // 二次确认——旧回答会被后端 delete_latest_assistant 永久删除，手抖点错
    // 不可恢复。confirm 比 toast undo 简单且不需要撤销栈基础设施。
    if (!window.confirm('重新生成会替换掉这条回答，确定要重新生成吗？')) return;
    setInput('');
    setChatError(null);
    setChatTrace(null);
    cancelEditUserMessage();
    prepareChatRegeneration(index, q);
    await send(q, { retry: true });
  }

  async function send(text, options = {}) {
    const retry = options.retry === true;
    const q = String(text ?? inputRef.current?.value ?? input).trim();
    if (!q || chatStreaming || guaStreaming) return;
    const sendStartedAt = Date.now();
    devLog(`[chat] send:start retry=${retry} at=${sendStartedAt}`);
    setChatError(null);

    // K 线一次性上下文：本次 send 把它挂到 client_context.kline 一起送出
    // （在下面的 streamMessage 调用里合并）。retry 不带 — 重发的语义是
    // "再问一遍"，不重新贴 context。
    const klineContextOnce = !retry ? klineContextRef.current : null;
    if (klineContextOnce) {
      klineContextRef.current = null;
      setKlineContextLabel(null);
    }
    const enrichedClientContext = klineContextOnce
      ? { ...clientContext, kline: klineContextOnce }
      : clientContext;

    if (!llmEnabled) {
      if (retry) {
        replaceLastAssistant('（未配置 LLM，当前回到预设回复）');
      } else {
        setInput('');
        if (currentConversationId) inputDraftRef.current.delete(currentConversationId);
        pushChat({ role: 'user', content: q });
        pushChat({ role: 'assistant', content: '' });
        replaceLastAssistant('（未配置 LLM，当前回到预设回复）');
      }
      return;
    }

    devLog(`[chat] ensureConversation:start dt=0ms`);
    const convId = await ensureConversationId();
    devLog(`[chat] ensureConversation:ready conv=${convId || 'none'} dt=${Date.now() - sendStartedAt}ms`);
    if (retry) {
      replaceLastAssistant('');
    } else {
      setInput('');
      if (convId) inputDraftRef.current.delete(convId);
      pushChat({ role: 'user', content: q });
      pushChat({ role: 'assistant', content: '' });
    }
    forceFollowNextRender();

    if (!convId) {
      replaceLastAssistant('（请先创建一个对话）');
      return;
    }

    setChatStreaming(true);
    beginTrace();
    resetThinkingForNewStream();
    const controller = bindStreamController();
    try {
      devLog(`[chat] stream:start conv=${convId} dt=${Date.now() - sendStartedAt}ms`);
      await streamMessage(convId, { message: q, bypass_divination: false, regenerate: retry, client_context: enrichedClientContext }, {
        signal: controller.signal,
        onDelta: (_t, running) => {
          scheduleAssistantDelta(running);
        },
        onThinking: (_t, running) => {
          appendThinkingDelta(running);
        },
        onIntent: (intent, reason, source, plan) =>
        {
          devLog(`[chat] intent=${intent} reason=${reason} source=${source}`);
          updateTrace({
            type: 'intent',
            intent,
            reason,
            source,
            needs: plan?.needs,
            retrieval_plan: plan?.retrieval_plan,
            // compound retrieval 用 router 多 intent 时,后端 SSE 在 intent
            // 事件里多送 retrieval_kinds 字段(主+副 intent 列表),前端
            // ThinkingIndicator 据此渲染"命理概念 ＋性格"双标签。这里
            // 必须把字段透传给 updateTrace,否则 chatProgress 拿不到。
            retrieval_kinds: plan?.retrieval_kinds,
          });
        },
        onRedirect: (to, redirQ) => {
          setChatTrace(null);
          if (to === 'gua') replacePlaceholderWithCta(redirQ || q, false);
          forceFollowNextRender();
        },
        onModel: (m) => {
          devLog('[chat] modelUsed=' + m);
          updateTrace({ type: 'model', modelUsed: m });
        },
        onRetrieval: (src) => {
          devLog('[chat] retrieval=' + src);
          updateTrace({ type: 'retrieval', source: src });
        },
        onDone: (full, finishReason) => {
          flushAssistantDelta();
          // finishReason === 'length' 表示模型被 max_tokens 截断；给最后这条
          // assistant 盖上 finish_reason，渲染层显示截断警示+续写按钮。即使
          // full 空（thinking 吃光配额的极端 case），也要标记便于续写。
          const extra = finishReason === 'length' ? { finish_reason: 'length' } : null;
          if (full || extra) replaceLastAssistant(full || '', extra);
          forceFollowNextRender();
          updateTrace({ type: 'done' });
          endThinkingStream();
        },
        onSuggestions: (items) => {
          devLog('[chat] suggestions received:', items);
          if (Array.isArray(items) && items.length > 0) {
            replaceLastAssistant(undefined, { suggestions: items });
          }
        },
      });
      bumpQuotaUsage('chat_message');
    } catch (e) {
      if (isAbortError(e)) {
        flushAssistantDelta();
        // 主动停止 → 给 last assistant 盖 finish_reason='stop_user'（后端
        // finally 也会落同样 meta 到 DB，下次刷历史仍能看到 banner）。
        // content 传 undefined 保留 onDelta 累积进来的 partial 文字。
        replaceLastAssistant(undefined, { finish_reason: 'stop_user' });
        updateTrace({ type: 'abort' });
        return;
      }
      console.error('[chat] failed:', e);
      const uiError = friendlyError(e, 'chat');
      replaceLastAssistant(uiError.title);
      setChatError({ error: e, question: q });
      // QUOTA_EXCEEDED / CHART_LIMIT_EXCEEDED — friendlyError 给挂上 cta，
      // 弹个 toast 让用户看到"查看订阅方案"那个按钮。
      if (uiError.cta) setAppNotice(uiError);
    } finally {
      releaseStreamController(controller);
      finalizeChatTurn({ setChatStreaming });
    }
  }

  async function castGuaInline(question) {
    if (!question?.trim() || guaStreaming || chatStreaming) return;
    const convId = await ensureConversationId();
    if (!convId) return;
    setGuaStreaming(true);
    const controller = bindStreamController();

    let guaData = null;
    let runningBody = '';
    try {
      const final = await streamGua(convId, { question: question.trim() }, {
        signal: controller.signal,
        onGua: (g) => {
          guaData = g;
          pushGuaCard({ ...g, question: question.trim(), body: '' });
          forceFollowNextRender();
        },
        onDelta: (_t, running) => {
          runningBody = running;
          updateLastGuaCard(running, false);
          forceFollowNextRender();
        },
        onModel: (m) => devLog('[gua] model=' + m),
      });
      const finalBody = final || runningBody;
      updateLastGuaCard(finalBody, true);
      forceFollowNextRender();
      setGuaCurrent({ ...(guaData || {}), question: question.trim(), body: finalBody, ts: Date.now() });
      // Note: gua history is now server-backed (each gua becomes a role='gua' message);
      // we no longer call pushGuaHistory.
      bumpQuotaUsage('gua');
    } catch (e) {
      if (isAbortError(e)) {
        updateLastGuaCard(runningBody || '（已停止输出）', true);
        return;
      }
      console.error('[gua inline] failed:', e);
      const ui = friendlyError(e, 'gua');
      updateLastGuaCard('（起卦失败：' + (ui.title || e.message || String(e)) + '）', true);
      if (ui.cta) setAppNotice(ui);
    } finally {
      releaseStreamController(controller);
      setGuaStreaming(false);
    }
  }

  async function analyzeDirectly(question) {
    if (!question?.trim() || chatStreaming || guaStreaming) return;
    setChatError(null);
    replaceLastCtaWithAssistant();
    setChatStreaming(true);
    beginTrace();
    const convId = await ensureConversationId();
    if (!convId) {
      setChatTrace(null);
      setChatStreaming(false);
      return;
    }
    const controller = bindStreamController();
    try {
      await streamMessage(convId, { message: question, bypass_divination: true, client_context: clientContext }, {
        signal: controller.signal,
        onDelta: (_t, running) => {
          scheduleAssistantDelta(running);
        },
        onIntent: (intent, reason, source) => {
          devLog(`[chat] analyze intent=${intent} reason=${reason} source=${source}`);
          updateTrace({ type: 'intent', intent, reason, source });
        },
        onModel: (m) => {
          devLog('[chat] analyze model=' + m);
          updateTrace({ type: 'model', modelUsed: m });
        },
        onRetrieval: (src) => {
          devLog('[chat] retrieval=' + src);
          updateTrace({ type: 'retrieval', source: src });
        },
        onDone: (full, finishReason) => {
          flushAssistantDelta();
          // finishReason === 'length' 表示模型被 max_tokens 截断；给最后这条
          // assistant 盖上 finish_reason，渲染层显示截断警示+续写按钮。即使
          // full 空（thinking 吃光配额的极端 case），也要标记便于续写。
          const extra = finishReason === 'length' ? { finish_reason: 'length' } : null;
          if (full || extra) replaceLastAssistant(full || '', extra);
          forceFollowNextRender();
          updateTrace({ type: 'done' });
          endThinkingStream();
        },
        onSuggestions: (items) => {
          devLog('[chat] analyze suggestions received:', items);
          if (Array.isArray(items) && items.length > 0) {
            replaceLastAssistant(undefined, { suggestions: items });
          }
        },
      });
      bumpQuotaUsage('chat_message');
    } catch (e) {
      if (isAbortError(e)) {
        flushAssistantDelta();
        // 主动停止 → 给 last assistant 盖 finish_reason='stop_user'（后端
        // finally 也会落同样 meta 到 DB，下次刷历史仍能看到 banner）。
        // content 传 undefined 保留 onDelta 累积进来的 partial 文字。
        replaceLastAssistant(undefined, { finish_reason: 'stop_user' });
        updateTrace({ type: 'abort' });
        return;
      }
      console.error('[analyze] failed:', e);
      const uiError = friendlyError(e, 'chat');
      replaceLastAssistant(uiError.title);
      setChatError({ error: e, question });
      if (uiError.cta) setAppNotice(uiError);
    } finally {
      releaseStreamController(controller);
      finalizeChatTurn({ setChatStreaming });
    }
  }

  function onKey(e) {
    // IME 合成阶段（中文/日文输入法正在选词）的 Enter 是确认候选词，不是发送。
    // e.nativeEvent.isComposing 是 W3C 标准；e.keyCode === 229 是老浏览器兜底。
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) {
      e.preventDefault();
      // 生成中按 Enter 既不发送也不停止——必须先点"停止"按钮中断，busy 变
      // false 后才能发新一条。这跟 ChatGPT/Claude 的行为对齐，避免用户在
      // streaming 中边打草稿边按 Enter 误把生成打断或半句话错发出去。
      if (chatStreaming || guaStreaming) return;
      send();
    }
  }

  const busy = chatStreaming || guaStreaming;
  const traceVisible = !!chatTrace && !chatTrace.hasOutput && (chatStreaming || chatTrace.phase === 'stopped');
  // Rotate the placeholder only when idle + empty + no context pill + not focused.
  const placeholderRotating = !busy && !input && !activeContextLabel && !inputFocused;
  useEffect(() => {
    if (!placeholderRotating) return undefined;
    const handle = setInterval(() => {
      setExampleIdx((current) => {
        // 标记当前为已展示，已全部走过则 reset（保留 current 一条避免立即回环）
        const shown = shownExampleIdxRef.current;
        shown.add(current);
        if (shown.size >= PROMPT_EXAMPLES.length) {
          shownExampleIdxRef.current = new Set([current]);
        }
        const remaining = [];
        for (let i = 0; i < PROMPT_EXAMPLES.length; i++) {
          if (!shownExampleIdxRef.current.has(i)) remaining.push(i);
        }
        if (remaining.length === 0) return current;
        return remaining[Math.floor(Math.random() * remaining.length)];
      });
    }, PROMPT_ROTATE_INTERVAL_MS);
    return () => clearInterval(handle);
  }, [placeholderRotating]);

  // 空态首次出现时点燃 800ms "正在读这张盘…" 入场。
  // - 仅当 history 为空、且非合盘 conversation 时触发
  // - 同一个 conversation 只触发一次（切走再回来不再播）
  // - currentConversationId 为 null 时（未建会话兜底）用 '__no_conv__' 占位
  useEffect(() => {
    if (history.length > 0 || hepanFocus) return undefined;
    const convKey = currentConversationId || '__no_conv__';
    if (readingShownConvRef.current.has(convKey)) return undefined;
    readingShownConvRef.current.add(convKey);
    setChartReading(true);
    const t = setTimeout(() => setChartReading(false), 800);
    return () => clearTimeout(t);
  }, [currentConversationId, history.length, hepanFocus]);

  const placeholderText = busy
    ? '生成中…可以先打下一句草稿，发送时先点停止'
    : activeContextLabel
      ? '继续追问这一点…'
      : PROMPT_EXAMPLES[exampleIdx];

  return (
    <div className="right-pane">
      <div className="chat-topbar">
        <div className="section-num">对 话</div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          <ConversationSwitcher disabled={busy} />
          <button
            className="muted"
            style={{ fontSize: 11 }}
            onClick={async () => {
              const chartId = useAppStore.getState().currentId;
              if (!chartId) return;
              const count = (useAppStore.getState().conversations || []).length;
              await newConversationOnServer(chartId, `对话 ${count + 1}`);
            }}
            disabled={busy}
            title="新建对话"
          >新对话</button>
        </div>
      </div>

      <div className="chat-body" ref={bodyRef} onScroll={onChatScroll}>
        {chatHistoryHasMore ? (
          <div ref={olderSentinelRef} className="chat-load-sentinel">
            {chatHistoryLoadingOlder ? (
              <span className="chat-loading-older">载入更早消息…</span>
            ) : null}
          </div>
        ) : null}
        {history.length === 0 && (
          <div className="chat-welcome fade-in">
            <div className="chat-opening-guide">
              {/* 空态第一帧 — Hepan 走自己的 4-chip CTA；单盘/大运/流年走
                  workspace.openingLine（一句 AI 开场，用盘里的事实 + 二选一钩子）
                  + workspace.openingChips（三个 chip）。
                  两种形态共用 .chat-opening-guide 容器（左 border pull-quote），
                  但内部布局不同：Hepan 老式 lead 文字 + chip row；
                  单盘新式 headline / body / chip row。 */}
              {hepanFocus ? (
                <>
                  <p className="chat-opening-lead">
                    <strong>合盘已接入对话</strong>
                    {`。正在围绕 ${activeContextLabel} 回答。`}
                  </p>
                  <div className="chat-hepan-suggestions">
                    <p className="chat-hepan-suggestions-kicker">试试问</p>
                    <div className="chat-hepan-suggestions-row">
                      <button
                        type="button"
                        className="chat-hepan-chip chat-hepan-chip-primary"
                        onClick={() => send('请给我一段关于这段关系的完整解读,600 字左右,包含核心动力、容易撞墙的地方、怎么调成最舒服的频率,以及一句话总结。')}
                      >完整解读 →</button>
                      <button
                        type="button"
                        className="chat-hepan-chip"
                        onClick={() => send('我们的核心动力是什么?')}
                      >核心动力</button>
                      <button
                        type="button"
                        className="chat-hepan-chip"
                        onClick={() => send('我们容易撞墙在哪里?')}
                      >容易撞墙</button>
                      <button
                        type="button"
                        className="chat-hepan-chip"
                        onClick={() => send('怎么把我们调成最舒服的频率?')}
                      >调到舒服</button>
                    </div>
                  </div>
                </>
              ) : chartReading ? (
                // 800ms 入场：让"AI 在读这张盘"先占住右栏一拍，再 fade 到开场
                <div className="chat-opening-reading" role="status" aria-live="polite">
                  <span className="chat-opening-reading-dot" aria-hidden="true" />
                  <span className="chat-opening-reading-text">正在读这张盘…</span>
                </div>
              ) : (
                <div className="chat-opening-reveal">
                  {workspace.openingLine?.headline ? (
                    <p className="chat-opening-headline">{workspace.openingLine.headline}</p>
                  ) : null}
                  <p className="chat-opening-body">{workspace.openingLine?.body}</p>
                  {workspace.openingChips?.length ? (
                    <div className="chat-hepan-suggestions">
                      <p className="chat-hepan-suggestions-kicker">从这里开口</p>
                      <div className="chat-hepan-suggestions-row">
                        {workspace.openingChips.map((chip, idx) => (
                          <button
                            type="button"
                            key={chip.label}
                            className={`chat-hepan-chip${idx === 0 ? ' chat-hepan-chip-primary' : ''}`}
                            onClick={() => send(chip.prompt)}
                            disabled={busy}
                          >{chip.label}{idx === 0 ? ' →' : ''}</button>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          </div>
        )}
        {history.map((m, i) => {
          if (m.role === 'user') {
            const isEditing = editingUserIndex === i;
            if (isEditing) {
              return (
                <div className="msg msg-user msg-user-editing" key={i}>
                  <div className="chat-edit-card">
                    <textarea
                      value={editingText}
                      onChange={(e) => setEditingText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Escape') cancelEditUserMessage();
                        // IME 合成中按 Enter 是选词，不应触发 cmd/ctrl+Enter 提交
                        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)
                            && !e.nativeEvent.isComposing && e.keyCode !== 229) {
                          e.preventDefault();
                          regenerateFromUser(i, editingText);
                        }
                      }}
                      rows={3}
                      autoFocus
                    />
                    {/* 编辑态保留文字按钮 — 这是主操作不该藏；icon 形态只
                        给静态消息上的"次操作"用 */}
                    <div className="chat-edit-actions">
                      <button
                        type="button"
                        className="btn-primary chat-edit-confirm"
                        onClick={() => regenerateFromUser(i, editingText)}
                        disabled={!String(editingText).trim() || busy}
                      >重新回答</button>
                      <button
                        type="button"
                        className="btn-inline"
                        onClick={cancelEditUserMessage}
                        disabled={busy}
                      >取消</button>
                    </div>
                  </div>
                </div>
              );
            }
            const userKey = `u-${i}`;
            const userCopied = copiedKey === userKey;
            return (
              <div className="msg msg-user" key={i}>
                <span className="bubble">{m.content}</span>
                <div className="msg-actions msg-actions-user">
                  {m.ts ? (
                    <span className="msg-time" title={new Date(m.ts).toLocaleString()}>
                      {_relativeTime(m.ts)}
                    </span>
                  ) : null}
                  <IconButton
                    icon={userCopied ? 'check' : 'copy'}
                    label={userCopied ? '已复制' : '复制'}
                    onClick={async () => {
                      const ok = await _copyToClipboard(m.content || '');
                      if (ok) {
                        setCopiedKey(userKey);
                        setTimeout(() => setCopiedKey((k) => (k === userKey ? null : k)), 1400);
                      }
                    }}
                  />
                  <IconButton
                    icon="edit"
                    label="修改问题"
                    onClick={() => beginEditUserMessage(i, m.content)}
                    disabled={busy}
                  />
                </div>
              </div>
            );
          }

          if (m.role === 'gua') {
            return (
              <div className="msg msg-ai" key={i}>
                <GuaCard data={m.content} />
              </div>
            );
          }

          if (m.role === 'cta') {
            const { question: ctaQ, manual } = m.content || {};
            return (
              <div className="msg msg-ai" key={i}>
                <CtaBubble
                  question={ctaQ}
                  manual={manual}
                  onCast={(q) => castGuaInline(q)}
                  onAnalyze={(q) => analyzeDirectly(q)}
                  disabled={busy}
                />
              </div>
            );
          }

          const isLast = i === history.length - 1;
          if (isLast && chatError) {
            const uiError = friendlyError(chatError.error, 'chat');
            return (
              <div className="msg msg-ai" key={i}>
                <ErrorState
                  title={uiError.title}
                  detail={uiError.detail}
                  retryable={uiError.retryable}
                  onRetry={uiError.retryable ? () => send(chatError.question, { retry: true }) : undefined}
                />
              </div>
            );
          }
          return (
            <div className="msg msg-ai" key={i}>
              <div className={'msg-ai-card' + (!m.content && !(isLast && traceVisible) ? ' loading' : '')}>
                {isLast && traceVisible ? (
                  <ThinkingIndicator trace={chatTrace} />
                ) : null}
                {isLast && thinking.text ? (
                  <ReasoningPanel
                    text={thinking.text}
                    streaming={thinking.streaming}
                    expanded={thinking.expanded}
                    startedAt={thinking.startedAt}
                    endedAt={thinking.endedAt}
                    onToggle={toggleThinkingExpanded}
                  />
                ) : null}
                <div className="msg-ai-body">
                  {m.content ? (
                    <RichText
                      text={m.content}
                      context={history[findPreviousUserIndex(history, i)]?.content || ''}
                      streaming={isLast && chatStreaming}
                    />
                  ) : null}
                </div>
                {(m.finish_reason === 'length' || m.finish_reason === 'stop_user')
                  && !(isLast && chatStreaming) ? (
                  <div className="msg-truncated-banner">
                    <span className="msg-truncated-icon" aria-hidden="true">⚠</span>
                    <span className="msg-truncated-text">
                      {m.finish_reason === 'length'
                        ? '回答过长被截断（达到模型输出上限）'
                        : '已停止生成'}
                    </span>
                    <button
                      type="button"
                      className="btn-inline msg-continue-btn"
                      onClick={() => send('继续')}
                      disabled={busy}
                    >
                      {m.finish_reason === 'length' ? '续写' : '接着写'}
                    </button>
                  </div>
                ) : null}
                {isLast && m.suggestions && m.suggestions.length > 0 && !chatStreaming ? (
                  <div className="msg-suggestions">
                    {m.suggestions.map((q, si) => (
                      <button
                        key={si}
                        type="button"
                        className="msg-suggestion-chip"
                        onClick={() => {
                          // 不直接发——填进输入框让用户改/确认后再发
                          setInput(q);
                          requestAnimationFrame(() => {
                            const el = inputRef.current;
                            if (!el) return;
                            el.focus();
                            try { el.setSelectionRange(q.length, q.length); } catch { /* ignore */ }
                          });
                        }}
                        disabled={busy}
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
              {(() => {
                const userIndex = findPreviousUserIndex(history, i);
                if (userIndex < 0) return null;
                const question = history[userIndex]?.content || '';
                const aiKey = `a-${i}`;
                const aiCopied = copiedKey === aiKey;
                const streaming = isLast && busy;
                // 流式中只露"停止"按钮 —— 复制 / 重答都是"完成态"才有意义
                if (streaming) {
                  return (
                    <div className="msg-actions msg-actions-ai msg-actions-streaming">
                      <IconButton icon="stop" label="停止生成" onClick={stopStreaming} />
                    </div>
                  );
                }
                // 没内容（占位 placeholder 或空消息）— 没东西可复制 / 重答
                if (!m.content) return null;
                return (
                  <>
                    <div className="msg-actions msg-actions-ai">
                      <IconButton
                        icon={aiCopied ? 'check' : 'copy'}
                        label={aiCopied ? '已复制' : '复制'}
                        // busy 中（任意流式）禁用——避免复制半截 partial 内容
                        disabled={busy}
                        onClick={async () => {
                          const ok = await _copyToClipboard(m.content || '');
                          if (ok) {
                            setCopiedKey(aiKey);
                            setTimeout(() => setCopiedKey((k) => (k === aiKey ? null : k)), 1400);
                          }
                        }}
                      />
                      <IconButton
                        icon="refresh"
                        label="重新回答"
                        // busy 中点击会被 regenerateFromUser 内部 guard 静默吞掉；
                        // 显式 disabled 让 UI 状态一致——用户能看出"现在不能点"
                        disabled={busy}
                        onClick={() => regenerateFromUser(userIndex, question)}
                      />
                      {m.ts ? (
                        <span className="msg-time" title={new Date(m.ts).toLocaleString()}>
                          {_relativeTime(m.ts)}
                        </span>
                      ) : null}
                    </div>
                  </>
                );
              })()}
            </div>
          );
        })}
      </div>

      {showJumpToBottom ? (
        <button
          type="button"
          className="chat-jump-bottom"
          onClick={jumpToBottom}
          aria-label="回到底部"
          title="回到底部"
        >
          <span className="chat-jump-bottom-arrow" aria-hidden="true">↓</span>
          <span className="chat-jump-bottom-label">新内容</span>
        </button>
      ) : null}

      <div className="chat-input-wrap">
        {klineContextLabel ? (
          <div className="chat-context-pill chat-context-pill-kline" role="status">
            <span className="chat-context-pill-prefix" aria-hidden="true">附</span>
            <span className="chat-context-pill-label">{klineContextLabel}</span>
            <button
              type="button"
              className="chat-context-pill-close"
              onClick={clearKlineContext}
              aria-label="撤销 K 线附带的上下文"
              title="撤销 K 线附带的上下文"
              // 关闭 pill 只是 UI 状态清理，跟 streaming 无关——busy 中也允许关
            >×</button>
          </div>
        ) : null}
        {activeContextLabel ? (
          <div className="chat-context-pill" role="status">
            <span className="chat-context-pill-prefix" aria-hidden="true">聚焦</span>
            {hepanFocus?.a && hepanFocus?.b ? (
              <span className="chat-context-pill-pair">
                <AvatarBadge
                  size={18}
                  seed={hepanFocus.a.seed}
                  name={hepanFocus.a.name}
                  avatarUrl={hepanFocus.a.avatarUrl}
                  className="chat-context-pill-avatar"
                />
                <span className="chat-context-pill-name">{hepanFocus.a.name}</span>
                <span className="chat-context-pill-x" aria-hidden="true">×</span>
                <AvatarBadge
                  size={18}
                  seed={hepanFocus.b.seed}
                  name={hepanFocus.b.name}
                  avatarUrl={hepanFocus.b.avatarUrl}
                  className="chat-context-pill-avatar"
                />
                <span className="chat-context-pill-name">{hepanFocus.b.name}</span>
              </span>
            ) : (
              <span className="chat-context-pill-label">{activeContextLabel}</span>
            )}
            {hepanFocus ? null : (
              <button
                type="button"
                className="chat-context-pill-close"
                onClick={clearActiveContext}
                aria-label="退出当前聚焦"
                title="退出当前聚焦，回到整盘对话"
                disabled={busy}
              >×</button>
            )}
          </div>
        ) : null}
        <div className="chat-input">
          <div className="chat-textarea-wrap">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
              onFocus={() => setInputFocused(true)}
              onBlur={() => setInputFocused(false)}
              rows={1}
              placeholder=""
              // 生成中也允许输入——用户可以提前打下一条草稿。要发送时先点"停止"
              // 按钮中断当前回答，busy 变 false 之后再按 Enter 才会真正发送。
              // 见 onKey() 里的 busy 分支。
            />
            {!input ? (
              <div
                className="chat-placeholder-overlay"
                aria-hidden="true"
                key={placeholderRotating ? exampleIdx : placeholderText}
              >
                {placeholderText}
              </div>
            ) : null}
          </div>
          <button
            className="btn-primary chat-send-btn"
            onClick={busy ? stopStreaming : () => send()}
            disabled={busy ? false : !String(input).trim()}
          >
            {busy ? '停止' : '发送'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── 模型推演面板 ─────────────────────────────────────────────────
//
// 渲染上面 send() 里维护的 thinking state。流式时默认展开，第一个答案
// token 到时自动收起（applyAssistantDelta 里把 expanded 改 false）。用户
// 之后可以再点开复看 — toggle 是用户主动行为，不再触发自动收起。
//
// 视觉上：折叠时只有一行 disclosure（"已推演 N 秒 ▾"），展开是一块
// 小字、灰底、无衬线、可滚动；不喧宾夺主，跟正文气泡有清晰层级。
function ReasoningPanel({ text, streaming, expanded, startedAt, endedAt, onToggle }) {
  // 流式时每 500ms 滴答一次 — 把"已推演 X 秒"的当前时间塞进 state，
  // 避免在 render 里直接 Date.now()（react-hooks/purity 会拒绝）。
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    if (!streaming) return undefined;
    const id = setInterval(() => setNowMs(Date.now()), 500);
    return () => clearInterval(id);
  }, [streaming]);

  // 流式时自动把 panel 滚到底（跟着新 token 走）。用户手动拉上去之后就停 —
  // 跟 chat 主体 stickyScroll 的策略一致：距底超过阈值就视为用户在看上面。
  const bodyRef = useRef(null);
  useEffect(() => {
    const el = bodyRef.current;
    if (!el || !streaming || !expanded) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distance < 60) {
      el.scrollTop = el.scrollHeight;
    }
  }, [text, streaming, expanded]);

  const elapsedMs = (endedAt || (streaming ? nowMs : startedAt)) - startedAt;
  const seconds = Math.max(0, Math.floor(elapsedMs / 1000));
  const headerLabel = streaming
    ? (seconds > 0 ? `推演中 · ${seconds} 秒` : '推演中…')
    : `已推演 ${seconds} 秒`;

  return (
    <div className={'reasoning-panel' + (expanded ? ' is-open' : '') + (streaming ? ' is-streaming' : '')}>
      <button
        type="button"
        className="reasoning-toggle"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-label={expanded ? '收起推演过程' : '展开推演过程'}
      >
        <span className="reasoning-dot" aria-hidden="true" />
        <span className="reasoning-toggle-label">{headerLabel}</span>
        <span className="reasoning-caret" aria-hidden="true">{expanded ? '▾' : '▸'}</span>
      </button>
      <div className="reasoning-body" ref={bodyRef} hidden={!expanded}>
        <div className="reasoning-text">{text}</div>
      </div>
    </div>
  );
}
