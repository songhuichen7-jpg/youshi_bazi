import { create } from 'zustand';
import { SESSION_VERSION } from '../lib/constants.js';
import { streamVerdicts } from '../lib/api.js';
import { clearAuthSessionHint } from '../lib/authSessionHint.js';
import { clearAuthPhoneHint } from '../lib/authPhoneHint.js';
import { appendChatMessage, trimChatHistory } from '../lib/chatHistory.js';
import { clearSession } from '../lib/persistence.js';
import { chartListItemToEntry, chartResponseToEntry } from '../lib/chartUi.js';

export const CLASSICS_VERSION = 'persona-verdict-v12';

async function restoreGuestAfterAuthFailure(set) {
  clearAuthSessionHint();
  clearAuthPhoneHint();
  clearSession();
  clearClientSessionStorage();
  set({
    user: null,
    charts: {},
    currentId: null,
    ...makeBlankChart(),
  });

  try {
    const { readGuestToken, writeGuestToken } = await import('../lib/guestToken.js');
    const { guestLogin } = await import('../lib/api.js');
    const { setAuthSessionHint } = await import('../lib/authSessionHint.js');
    const result = await guestLogin({ guestToken: readGuestToken() });
    if (result?.guest_token) writeGuestToken(result.guest_token);
    if (result?.user) {
      setAuthSessionHint();
      set({ user: result.user });
      return result.user;
    }
  } catch {
    // Fall through to auth screen.
  }
  return null;
}

function _serverMsgToUiMsg(m) {
  // 服务端 created_at 保留下来 — 给 chat UI 渲染相对时间戳（"5 分钟前"）
  // 用。本地 push 的 message 在 pushChat / appendMessage 里补上 ts，让两条
  // 路的消息都能用同一个字段。
  const ts = m.created_at ? Date.parse(m.created_at) : null;
  if (m.role === 'gua') {
    const { gua, body, question } = m.meta || {};
    return { role: 'gua', content: { ...(gua || {}), body, question, streaming: false }, ts };
  }
  if (m.role === 'cta') {
    const { question } = m.meta || {};
    return { role: 'cta', content: { question, manual: false }, ts };
  }
  // assistant message 的 meta.finish_reason 提到顶层方便渲染层判断：
  //   "length"    → max_tokens 截断（系统行为）→ "续写"按钮
  //   "stop_user" → 用户主动点了停止（详见 conversation_chat.py finally 落库）
  //                 → "接着写"按钮
  //   "stop" / 缺失 → 正常完成，不显示截断标记
  const finishReason = m.meta?.finish_reason || null;
  const base = { role: m.role, content: m.content || '', ts };
  if (finishReason === 'length' || finishReason === 'stop_user') {
    base.finish_reason = finishReason;
  }
  const suggestions = m.meta?.suggestions;
  if (Array.isArray(suggestions) && suggestions.length > 0) {
    base.suggestions = suggestions;
  }
  return base;
}

function blankVerdicts() {
  return {
    status: 'idle',
    body: '',
    lastError: null,
  };
}

function blankClassics() {
  return {
    status: 'idle',
    persona: null,
    verdict: null,
    lastError: null,
    version: CLASSICS_VERSION,
  };
}

function hydrateVerdicts(verdicts) {
  if (!verdicts) return blankVerdicts();
  const body = typeof verdicts.body === 'string' ? verdicts.body : '';
  return {
    status: verdicts.status || (body ? 'done' : 'idle'),
    body,
    lastError: verdicts.lastError || null,
  };
}

function hydrateClassics(classics) {
  if (!classics) return blankClassics();
  if (classics.version !== CLASSICS_VERSION) return blankClassics();
  const persona = classics.persona && typeof classics.persona === 'object' ? classics.persona : null;
  const verdict = classics.verdict && typeof classics.verdict === 'object' ? classics.verdict : null;
  return {
    status: classics.status || ((persona || verdict) ? 'done' : 'idle'),
    persona,
    verdict,
    lastError: classics.lastError || null,
    version: classics.version || null,
  };
}

function chartStateFromEntry(entry, extra = {}) {
  return {
    ...makeBlankChart(),
    paipan: entry?.paipan || null,
    force: entry?.force || [],
    guards: entry?.guards || [],
    dayun: entry?.dayun || [],
    meta: entry?.meta || null,
    birthInfo: entry?.birthInfo || null,
    sections: entry?.sections || [],
    dayunCache: entry?.dayunCache || {},
    liunianCache: entry?.liunianCache || {},
    verdicts: hydrateVerdicts(entry?.verdicts),
    classics: hydrateClassics(entry?.classics),
    screen: 'shell',
    dayunOpenIdx: null,
    liunianOpenKey: null,
    ...extra,
  };
}

function readCurrentChartId() {
  try { return sessionStorage.getItem('currentChartId'); } catch { return null; }
}

function writeCurrentChartId(chartId) {
  try {
    if (chartId) sessionStorage.setItem('currentChartId', chartId);
    else sessionStorage.removeItem('currentChartId');
  } catch {
    // Ignore storage errors in private mode / SSR.
  }
}

function clearClientSessionStorage() {
  try {
    const keys = [];
    for (let index = 0; index < sessionStorage.length; index += 1) {
      const key = sessionStorage.key(index);
      if (key && (key === 'currentChartId' || key.startsWith('currentConversationId:'))) {
        keys.push(key);
      }
    }
    keys.forEach((key) => sessionStorage.removeItem(key));
  } catch {
    // Ignore storage errors in private mode / SSR.
  }
}

function updateChartVerdicts(state, chartId, updater) {
  const current = chartId === state.currentId
    ? hydrateVerdicts(state.verdicts)
    : hydrateVerdicts(state.charts[chartId]?.verdicts);
  const nextVerdicts = updater(current);
  const next = {};

  if (chartId === state.currentId) next.verdicts = nextVerdicts;
  if (chartId && state.charts[chartId]) {
    next.charts = {
      ...state.charts,
      [chartId]: { ...state.charts[chartId], verdicts: nextVerdicts },
    };
  }
  return next;
}

function updateChartClassics(state, chartId, updater) {
  const current = chartId === state.currentId
    ? hydrateClassics(state.classics)
    : hydrateClassics(state.charts[chartId]?.classics);
  const nextClassics = updater(current);
  const next = {};

  if (chartId === state.currentId) next.classics = nextClassics;
  if (chartId && state.charts[chartId]) {
    next.charts = {
      ...state.charts,
      [chartId]: { ...state.charts[chartId], classics: nextClassics },
    };
  }
  return next;
}

const conversationBootstrapPromises = new Map();
const classicsInFlight = new Map();

const BLANK_CHART = {
  paipan: null, force: [], guards: [], dayun: [], meta: null, birthInfo: null,
  sections: [],
  // Plan 6: chat data is server-of-truth; ephemeral here, never persisted
  chatHistory: [],
  // Chat history pagination — 后端 GET /messages 是 cursor-based 分页（limit 50
  // 每页）。loadMessages 拿首页 + next_cursor；用户滚到顶部时 fetchOlderChatMessages
  // 用 cursor 拉上一页 prepend。null cursor 表示已经到最早，无更多老消息。
  chatHistoryCursor: null,
  chatHistoryHasMore: false,
  chatHistoryLoadingOlder: false,
  conversations: [],
  currentConversationId: null,
  gua: { current: null, history: [] },   // ephemeral, not persisted
  dayunCache: {}, liunianCache: {},
  verdicts: blankVerdicts(),
  classics: blankClassics(),
};

function makeBlankChart() { return { ...BLANK_CHART }; }

export function generateChartLabel(formData) {
  if (!formData) return '新命盘';
  const g = formData.gender === 'female' ? '女' : '男';
  const d = formData.date || `${formData.year}-${String(formData.month||'').padStart(2,'0')}-${String(formData.day||'').padStart(2,'0')}`;
  const t = formData.time || (formData.hour != null && formData.hour !== -1 ? `${String(formData.hour).padStart(2,'0')}:${String(formData.minute||0).padStart(2,'0')}` : '');
  return `${g} · ${d}${t ? ' ' + t : ''}`;
}

// Snapshot current flat chart state for persistence.
function snapshotChart(s, extra = {}) {
  return {
    paipan: s.paipan, force: s.force, guards: s.guards,
    dayun: s.dayun, meta: s.meta, birthInfo: s.birthInfo,
    sections: s.sections,
    dayunCache: s.dayunCache, liunianCache: s.liunianCache,
    verdicts: s.verdicts,
    classics: s.classics,
    ...extra,
  };
}

const initialState = {
  screen: 'landing',
  view: 'chart',
  ...BLANK_CHART,
  user: null,
  // /api/auth/me 的 quota_snapshot — 用户中心、聊天报错时都要读。
  // bumpQuotaUsage 乐观推进；refreshQuotaSnapshot 拿权威值兜底纠偏。
  // ``quotaSnapshotFetchedAt`` 是毫秒时间戳，5 分钟过期由调用方决定要不要 refresh。
  quotaSnapshot: null,
  quotaSnapshotFetchedAt: 0,

  // Multi-chart index
  charts: {},      // Record<id, { id, label, createdAt, formData, ...chartFields }>
  currentId: null,

  // Transient UI (not per-chart, not persisted)
  dayunOpenIdx: null, liunianOpenKey: null,
  dayunStreaming: false, liunianStreaming: false,
  chatStreaming: false, guaStreaming: false,
  sectionsLoading: false, sectionsError: null,
  formError: null, loadingStage: 0,
  appNotice: null,
  llmEnabled: true,
  skipConversationHydration: false,
  cardModeHint: null,  // 'hepan' | 'single' | null — one-shot hint for CardWorkspace
  // K 线点击 → chat 的一次性 prefill payload。Chat 消费后立即清空。
  // { contextCard: string, prompt: string, nonce: number } | null
  chatPrefill: null,
};

export const useAppStore = create((set, get) => ({
  ...initialState,

  // ── Navigation ──────────────────────────────────────────────────────────────
  setScreen: (screen) => set({ screen }),
  setView:   (view)   => set({ view }),
  setCardModeHint: (hint) => set({ cardModeHint: hint }),
  // 把一段 K 线注入消息塞进 chat。Chat.jsx 在 effect 里读到后会插入到当前
  // 对话，并把输入框预填 prompt（用户可改）；消费完调用 clearChatPrefill。
  setChatPrefill: (payload) => set({
    chatPrefill: payload ? { ...payload, nonce: Date.now() } : null,
  }),
  clearChatPrefill: () => set({ chatPrefill: null }),
  setUser: (user) => set({ user }),
  // 部分字段更新 —— 用户中心改昵称 / 头像后只需要刷新这两项，
  // 不能用 setUser 整体覆盖（会把 phone 等已有字段冲掉，比如登录留下的 phone）。
  patchUser: (patch) => set((s) => ({
    user: s.user ? { ...s.user, ...patch } : (patch.id ? patch : s.user),
  })),
  enterFromLanding: async (options = {}) => {
    const state = get();
    if (!state.user) {
      // 没登录 — 但如果 localStorage 有 guest_token，先静默尝试用它
      // 复活 session（内测访客刷新或隔天回访都能直达，不用再过 AuthScreen）
      try {
        const { readGuestToken, writeGuestToken } = await import('../lib/guestToken.js');
        const { guestLogin } = await import('../lib/api.js');
        const { setAuthSessionHint } = await import('../lib/authSessionHint.js');
        const token = readGuestToken();
        if (token) {
          const result = await guestLogin({ guestToken: token });
          if (result?.guest_token) writeGuestToken(result.guest_token);
          if (result?.user) {
            setAuthSessionHint();
            set({ user: result.user });
            // 继续往下走 — 现在 state.user 有值了，逻辑跟登录用户一致
          }
        }
      } catch { /* 静默 — 走 AuthScreen 兜底 */ }
    }

    if (!get().user) {
      set({ screen: 'auth' });
      return 'auth';
    }

    const chartEntries = Object.values(state.charts || {});
    if (chartEntries.length === 0) {
      let items;
      try {
        items = await get().syncChartsFromServer();
      } catch (error) {
        if (error?.status === 401 && !options.retriedAuth) {
          const restored = await restoreGuestAfterAuthFailure(set);
          if (!restored) {
            set({ screen: 'auth' });
            return 'auth';
          }
          return get().enterFromLanding({ retriedAuth: true });
        }
        throw error;
      }
      if (!items.length) {
        set({ screen: 'input' });
        return 'input';
      }
      // syncChartsFromServer 调用 openChartFromServer 把命盘数据装好了，
      // 但它本身不动 screen — 这里显式落到 shell，避免回访用户落到 input。
      set({ screen: 'shell' });
      return 'shell';
    }

    const latest = chartEntries
      .slice()
      .sort((a, b) => (b?.createdAt || 0) - (a?.createdAt || 0))[0];
    const latestId = latest?.id;
    if (!latestId) {
      set({ screen: 'input' });
      return 'input';
    }

    if (latestId === state.currentId && state.paipan) {
      set({ screen: 'shell' });
      return 'shell';
    }

    if (latest?.paipan) {
      await get().switchChart(latestId);
      set({ screen: 'shell' });
      return 'shell';
    }

    const items = await get().syncChartsFromServer();
    if (!items.length) {
      set({ screen: 'input' });
      return 'input';
    }
    set({ screen: 'shell' });
    return 'shell';
  },
  setLlmStatus: (enabled) => set({ llmEnabled: enabled }),
  setFormError: (f)  => set({ formError: f }),
  setLoadingStage: (i) => set({ loadingStage: i }),
  setAppNotice: (notice) => set((s) => {
    if (!notice) return { appNotice: null };
    if (s.appNotice && s.appNotice.title === notice.title && s.appNotice.detail === notice.detail) {
      return s;
    }
    return { appNotice: { id: Date.now(), ...notice } };
  }),
  clearAppNotice: () => set({ appNotice: null }),

  // ── Quota（用量）── 配额状态在 /api/auth/me 的 quota_snapshot 上落地。
  setQuotaSnapshot: (snapshot) => set({
    quotaSnapshot: snapshot || null,
    quotaSnapshotFetchedAt: snapshot ? Date.now() : 0,
  }),
  // 乐观自增 — 在 chat / gua 调用 onDone 时调一次，不等 /me round trip。
  // periodic kind（chat_message / gua / regen / sms_send）+ chart 累计一起处理。
  bumpQuotaUsage: (kind, delta = 1) => set((s) => {
    if (!s.quotaSnapshot || !kind) return s;
    const next = { ...s.quotaSnapshot };
    if (kind === 'chart' && next.chart) {
      next.chart = { ...next.chart, used: (next.chart.used || 0) + delta };
    } else if (next.usage && next.usage[kind]) {
      next.usage = {
        ...next.usage,
        [kind]: { ...next.usage[kind], used: (next.usage[kind].used || 0) + delta },
      };
    } else {
      return s;     // 没这条 kind 就不改，免得脏写
    }
    return { quotaSnapshot: next };
  }),
  // 5 分钟内不重复拉；force=true 时无视缓存（quota 撞墙后调一次纠偏）。
  refreshQuotaSnapshot: async ({ force = false } = {}) => {
    const TTL_MS = 5 * 60 * 1000;
    const s = get();
    if (!force && s.quotaSnapshot && (Date.now() - s.quotaSnapshotFetchedAt) < TTL_MS) {
      return s.quotaSnapshot;
    }
    try {
      const { me } = await import('../lib/api.js');
      const result = await me();
      if (result?.quota_snapshot) {
        set({
          quotaSnapshot: result.quota_snapshot,
          quotaSnapshotFetchedAt: Date.now(),
        });
        return result.quota_snapshot;
      }
    } catch { /* 静默 — 用户中心可以暂时不显示用量条 */ }
    return null;
  },

  // ── Chart data (flat) ───────────────────────────────────────────────────────
  setBirthInfo: (birthInfo) => set({ birthInfo }),

  setSectionsLoading: (b) => set({ sectionsLoading: b }),
  setSectionsError:   (e) => set({ sectionsError: e }),
  setSections:        (sections) => set({ sections, sectionsError: null }),

  loadClassics: async (chartId) => {
    if (!chartId) return;
    // Dedup concurrent calls — the polisher does ~40s of LLM work and
    // overlapping requests would each return slightly different polished
    // text (LLM is not deterministic at temperature > 0). React StrictMode
    // double-invokes effects in dev, which without this dedup made the
    // panel "flash" the first result then overwrite it with the second.
    const inflight = classicsInFlight.get(chartId);
    if (inflight) return inflight;

    set((s) => updateChartClassics(s, chartId, () => ({
      status: 'loading',
      persona: null,
      verdict: null,
      lastError: null,
      version: CLASSICS_VERSION,
    })));

    const task = (async () => {
      try {
        const { fetchClassics } = await import('../lib/api.js');
        const data = await fetchClassics(chartId);
        set((s) => updateChartClassics(s, chartId, () => ({
          status: 'done',
          persona: data?.persona && typeof data.persona === 'object' ? data.persona : null,
          verdict: data?.verdict && typeof data.verdict === 'object' ? data.verdict : null,
          lastError: null,
          version: CLASSICS_VERSION,
        })));
      } catch (e) {
        const message = e.message || String(e);
        set((s) => updateChartClassics(s, chartId, (current) => ({
          ...current,
          status: 'error',
          lastError: message,
        })));
      } finally {
        classicsInFlight.delete(chartId);
      }
    })();
    classicsInFlight.set(chartId, task);
    return task;
  },

  loadVerdicts: async (chartId) => {
    if (!chartId) return;

    set((s) => updateChartVerdicts(s, chartId, () => ({
      status: 'streaming',
      body: '',
      lastError: null,
    })));

    try {
      await streamVerdicts(chartId, {
        onDelta: (text) => {
          set((s) => updateChartVerdicts(s, chartId, (current) => ({
            ...current,
            status: 'streaming',
            body: (current.body || '') + text,
            lastError: null,
          })));
        },
        onDone: (full) => {
          set((s) => updateChartVerdicts(s, chartId, (current) => ({
            ...current,
            status: 'done',
            body: full || current.body || '',
            lastError: null,
          })));
        },
      });
    } catch (e) {
      const message = e.message || String(e);
      set((s) => updateChartVerdicts(s, chartId, (current) => ({
        ...current,
        status: 'error',
        lastError: message,
      })));
    }
  },

  appendMessage: (msg) => set(s => ({
    chatHistory: [...s.chatHistory, msg.ts ? msg : { ...msg, ts: Date.now() }],
  })),
  pushChat: (msg) => set(s => {
    // 给本地 push 的消息盖一层 ts 戳，跟服务端 created_at 同语义。streaming
    // 占位的 assistant message 也会拿到 ts —— 流式完成后这条 ts 就是"本轮
    // 开始时间"，对 UI 上"5 秒前 → 1 分钟前" 的演进足够准。
    const stamped = msg.ts ? msg : { ...msg, ts: Date.now() };
    const chatHistory = appendChatMessage(s.chatHistory, stamped);
    return { chatHistory };
  }),
  replaceLastAssistant: (content, extra = null) => set(s => {
    // extra: 可选字段 patch（如 { finish_reason: 'length' }）。流式 onDone 给
    // 最后这条 assistant 盖上 finish_reason，渲染层据此显示截断警示+续写按钮。
    // content === undefined / null → 只 patch extra 不动现有内容（用于
    // abort 场景：用户主动停止时只想标记 finish_reason='stop_user'，保留
    // 已流入的 partial content）。
    const arr = s.chatHistory.slice();
    for (let i = arr.length - 1; i >= 0; i--) {
      if (arr[i].role === 'assistant') {
        const next = { ...arr[i], ...(extra || {}) };
        if (content !== undefined && content !== null) next.content = content;
        arr[i] = next;
        break;
      }
    }
    return { chatHistory: arr };
  }),
  prepareChatRegeneration: (userIndex, content) => set(s => {
    const index = Number(userIndex);
    const text = String(content ?? '').trim();
    if (!Number.isInteger(index) || index < 0 || !text || s.chatHistory[index]?.role !== 'user') {
      return {};
    }

    const chatHistory = s.chatHistory.slice(0, index + 1);
    chatHistory[index] = { ...chatHistory[index], content: text };
    chatHistory.push({ role: 'assistant', content: '' });
    return { chatHistory: trimChatHistory(chatHistory) };
  }),
  replaceLastCtaWithAssistant: () => set(s => {
    const arr = s.chatHistory.slice();
    for (let i = arr.length - 1; i >= 0; i--) {
      if (arr[i].role === 'cta') {
        arr[i] = { role: 'assistant', content: '' };
        break;
      }
    }
    return { chatHistory: arr };
  }),

  replacePlaceholderWithCta: (question, manual = false) => set(s => {
    const arr = s.chatHistory.slice();
    for (let i = arr.length - 1; i >= 0; i--) {
      if (arr[i].role === 'assistant') {
        arr[i] = { role: 'cta', content: { question, manual } };
        break;
      }
    }
    return { chatHistory: arr };
  }),

  pushGuaCard: (guaData) => set(s => {
    const chatHistory = appendChatMessage(s.chatHistory, {
      role: 'gua',
      content: { ...guaData, streaming: true },
    });
    return { chatHistory };
  }),

  updateLastGuaCard: (body, finalize = false) => set(s => {
    const arr = s.chatHistory.slice();
    for (let i = arr.length - 1; i >= 0; i--) {
      if (arr[i].role === 'gua') {
        arr[i] = {
          ...arr[i],
          content: {
            ...arr[i].content,
            body,
            streaming: finalize ? false : arr[i].content.streaming,
          },
        };
        break;
      }
    }
    return { chatHistory: arr };
  }),

  clearChat: () => set({ chatHistory: [] }),

  consumeCta: () => set(s => {
    const arr = s.chatHistory.slice();
    for (let i = arr.length - 1; i >= 0; i--) {
      if (arr[i].role === 'cta') { arr.splice(i, 1); break; }
    }
    return { chatHistory: arr };
  }),

  setChatStreaming: (b) => set({ chatStreaming: b }),

  // ── Conversations (server-backed) ────────────────────────────────────────
  loadConversations: async (chartId) => {
    const { listConversations } = await import('../lib/api.js');
    const data = await listConversations(chartId);
    const items = data.items || [];
    let currentId = null;
    try { currentId = sessionStorage.getItem('currentConversationId:' + chartId); } catch { /* SSR/private mode */ }
    if (!currentId || !items.some(c => c.id === currentId)) {
      currentId = items.length ? items[0].id : null;
    }
    set({ conversations: items, currentConversationId: currentId });
    return items;
  },

  selectConversation: async (convId) => {
    const s = get();
    if (s.currentId) {
      try { sessionStorage.setItem('currentConversationId:' + s.currentId, convId); } catch { /* SSR/private mode */ }
    }
    // 切对话立即 reset pagination state，避免 sentinel 用上一对话的
    // cursor/hasMore 误触发 fetchOlder。
    set({
      currentConversationId: convId,
      chatHistory: [],
      chatHistoryCursor: null,
      chatHistoryHasMore: false,
      chatHistoryLoadingOlder: false,
    });
    await get().loadMessages(convId);
  },

  loadMessages: async (convId) => {
    const { listMessages } = await import('../lib/api.js');
    const data = await listMessages(convId, { limit: 50 });
    const chrono = (data.items || []).slice().reverse();
    // next_cursor !== null → 还有更老的消息；用户滚到顶时调 fetchOlderChatMessages
    set({
      chatHistory: chrono.map(m => _serverMsgToUiMsg(m)),
      chatHistoryCursor: data.next_cursor || null,
      chatHistoryHasMore: !!data.next_cursor,
    });
  },

  fetchOlderChatMessages: async () => {
    const s = get();
    if (!s.currentConversationId || !s.chatHistoryHasMore || s.chatHistoryLoadingOlder) return;
    if (!s.chatHistoryCursor) return;
    set({ chatHistoryLoadingOlder: true });
    try {
      const { listMessages } = await import('../lib/api.js');
      const data = await listMessages(s.currentConversationId, {
        before: s.chatHistoryCursor,
        limit: 50,
      });
      const olderChrono = (data.items || []).slice().reverse();
      set((s2) => ({
        chatHistory: [...olderChrono.map(m => _serverMsgToUiMsg(m)), ...s2.chatHistory],
        chatHistoryCursor: data.next_cursor || null,
        chatHistoryHasMore: !!data.next_cursor,
      }));
    } finally {
      set({ chatHistoryLoadingOlder: false });
    }
  },

  ensureConversation: async (chartId) => {
    const targetChartId = chartId || get().currentId;
    if (!targetChartId) return { conversationId: null, created: false };

    if (conversationBootstrapPromises.has(targetChartId)) {
      return conversationBootstrapPromises.get(targetChartId);
    }

    const task = (async () => {
      const list = await get().loadConversations(targetChartId);
      let convId = get().currentConversationId;
      let created = false;

      if (!convId) {
        const conversation = await get().newConversationOnServer(targetChartId, `对话 ${list.length + 1}`);
        convId = conversation?.id || get().currentConversationId || null;
        created = true;
      }

      return { conversationId: convId, created };
    })().finally(() => {
      conversationBootstrapPromises.delete(targetChartId);
    });

    conversationBootstrapPromises.set(targetChartId, task);
    return task;
  },

  newConversationOnServer: async (chartId, label) => {
    const previous = {
      conversations: get().conversations || [],
      currentConversationId: get().currentConversationId,
      chatHistory: get().chatHistory,
    };
    const tempId = `temp-conv-${Date.now()}`;
    const now = new Date().toISOString();
    const optimisticConv = {
      id: tempId,
      chart_id: chartId,
      label,
      position: previous.conversations.length,
      created_at: now,
      updated_at: now,
      last_message_at: null,
      message_count: 0,
      deleted_at: null,
      optimistic: true,
    };

    set({
      conversations: [...previous.conversations, optimisticConv],
      currentConversationId: tempId,
      chatHistory: [],
    });

    try {
      const { createConversation } = await import('../lib/api.js');
      const conv = await createConversation(chartId, { label });
      try { sessionStorage.setItem('currentConversationId:' + chartId, conv.id); } catch { /* SSR/private mode */ }
      set((s) => ({
        conversations: (s.conversations || []).map((item) => item.id === tempId ? conv : item),
        currentConversationId: s.currentConversationId === tempId ? conv.id : s.currentConversationId,
      }));
      return conv;
    } catch (e) {
      set((s) => {
        const conversations = (s.conversations || []).filter((item) => item.id !== tempId);
        if (s.currentConversationId !== tempId) return { conversations };
        return {
          conversations: previous.conversations,
          currentConversationId: previous.currentConversationId,
          chatHistory: previous.chatHistory,
        };
      });
      throw e;
    }
  },

  // ensureHepanConversation —— "打开这条合盘的对话" 唯一入口。
  // 在当前 conversations 里找 hepan_slug 匹配的，没有就 POST 新建。
  // 副作用：会 setCurrentConversationId 到目标对话；调用方拿到 id 后
  // 自己负责 navigate(/app)。
  ensureHepanConversation: async (chartId, hepanSlug) => {
    if (!chartId || !hepanSlug) {
      throw new Error('ensureHepanConversation: chartId and hepanSlug required');
    }
    const existing = (get().conversations || []).find(
      c => c.hepan_slug === hepanSlug && !c.deleted_at,
    );
    if (existing) {
      try { sessionStorage.setItem('currentConversationId:' + chartId, existing.id); } catch { /* SSR */ }
      set({ currentConversationId: existing.id });
      return existing.id;
    }
    const { createConversation } = await import('../lib/api.js');
    const conv = await createConversation(chartId, { hepan_slug: hepanSlug });
    try { sessionStorage.setItem('currentConversationId:' + chartId, conv.id); } catch { /* SSR */ }
    set(s => ({
      conversations: [...(s.conversations || []), conv],
      currentConversationId: conv.id,
      chatHistory: [],
    }));
    return conv.id;
  },

  renameConversationOnServer: async (convId, label) => {
    const { patchConversation } = await import('../lib/api.js');
    const updated = await patchConversation(convId, label);
    set(s => ({
      conversations: (s.conversations || []).map(c => c.id === convId ? updated : c),
    }));
    return updated;
  },

  deleteConversationOnServer: async (chartId, convId) => {
    const { deleteConversation: apiDelete } = await import('../lib/api.js');
    await apiDelete(convId);
    const list = (get().conversations || []).filter(c => c.id !== convId);
    let nextId = get().currentConversationId;
    if (nextId === convId) {
      nextId = list[0]?.id || null;
      if (!nextId) {
        // 删除的是最后一个对话 → 自动新建一个空白对话。命名故意
        // 跟"对话 N"序列脱钩，否则用户会看到"我刚删的对话 1 又出现了"，
        // 误以为删除没生效。'新对话' 是中性占位，留给用户自行重命名。
        set({ conversations: [] });
        await get().newConversationOnServer(chartId, '新对话');
        return;
      }
      try { sessionStorage.setItem('currentConversationId:' + chartId, nextId); } catch { /* SSR/private mode */ }
    }
    set({ conversations: list, currentConversationId: nextId });
    if (nextId) await get().loadMessages(nextId);
  },

  setDayunCache: (idx, text) => set(s => ({ dayunCache: { ...s.dayunCache, [idx]: text } })),
  deleteDayunCache: (idx) => set(s => { const { [idx]: _, ...rest } = s.dayunCache; return { dayunCache: rest }; }),
  setDayunOpenIdx: (idx) => set({ dayunOpenIdx: idx }),
  setDayunStreaming: (b)  => set({ dayunStreaming: b }),

  setGuaCurrent: (current) => set(s => ({ gua: { ...(s.gua || {}), current } })),
  pushGuaHistory: (entry) => set(s => ({
    gua: { ...(s.gua || {}), history: [...(s.gua?.history || []), entry].slice(-20) },
  })),
  setGuaStreaming: (b) => set({ guaStreaming: b }),

  setLiunianCache: (key, text) => set(s => ({ liunianCache: { ...s.liunianCache, [key]: text } })),
  deleteLiunianCache: (key) => set(s => { const { [key]: _, ...rest } = s.liunianCache; return { liunianCache: rest }; }),
  setLiunianOpenKey: (key) => set({ liunianOpenKey: key }),
  setLiunianStreaming: (b)  => set({ liunianStreaming: b }),

  // ── Multi-chart management ────────────────────────────────────────────────
  openChartFromResponse: (response, options = {}) => {
    const nextId = response?.chart?.id;
    if (!nextId) return;
    writeCurrentChartId(nextId);
    set((state) => {
      const charts = options.preserveCurrent === false
        ? { ...state.charts }
        : (
            state.currentId && state.charts[state.currentId]
              ? {
                  ...state.charts,
                  [state.currentId]: { ...state.charts[state.currentId], ...snapshotChart(state) },
                }
              : { ...state.charts }
          );
      const previous = charts[nextId] || {};
      const mapped = chartResponseToEntry(response);
      const entry = {
        ...makeBlankChart(),
        ...previous,
        ...mapped,
        sections: previous.sections || [],
        dayunCache: previous.dayunCache || {},
        liunianCache: previous.liunianCache || {},
        verdicts: previous.verdicts || blankVerdicts(),
        classics: previous.classics || blankClassics(),
      };
      charts[nextId] = entry;
      return {
        charts,
        currentId: nextId,
        skipConversationHydration: !!options.skipConversationHydration,
        ...chartStateFromEntry(entry),
      };
    });
  },

  openChartFromServer: async (id) => {
    const { getChart } = await import('../lib/api.js');
    const response = await getChart(id);
    get().openChartFromResponse(response);
    return response;
  },

  syncChartsFromServer: async () => {
    const { listCharts } = await import('../lib/api.js');
    clearSession();
    const data = await listCharts();
    const items = data.items || [];
    const previousCharts = get().charts || {};
    const charts = {};
    items.forEach((item) => {
      charts[item.id] = {
        ...makeBlankChart(),
        ...(previousCharts[item.id] || {}),
        ...chartListItemToEntry(item),
      };
    });
    if (!items.length) {
      writeCurrentChartId(null);
      set({
        charts: {},
        currentId: null,
        ...makeBlankChart(),
        screen: 'input',
        view: 'chart',
      });
      return [];
    }
    const storedId = readCurrentChartId();
    const nextId = storedId && charts[storedId] ? storedId : items[0].id;
    set({ charts, currentId: null });
    await get().openChartFromServer(nextId);
    return items;
  },

  switchChart: async (id) => {
    const s = get();
    if (id === s.currentId) return;
    const target = s.charts[id];
    if (!target) return;
    if (!target.paipan) {
      await get().openChartFromServer(id);
      return;
    }
    writeCurrentChartId(id);
    set((state) => {
      const charts = state.currentId && state.charts[state.currentId]
        ? {
            ...state.charts,
            [state.currentId]: { ...state.charts[state.currentId], ...snapshotChart(state) },
          }
        : { ...state.charts };
      const nextEntry = charts[id];
      return {
        charts,
        currentId: id,
        skipConversationHydration: false,
        ...chartStateFromEntry(nextEntry),
      };
    });
  },

  deleteChart: async (id) => {
    const { deleteChart: deleteChartApi } = await import('../lib/api.js');
    await deleteChartApi(id);
    const s = get();
    const charts = { ...s.charts };
    delete charts[id];
    const ids = Object.keys(charts).sort((a,b) => (charts[b].createdAt||0) - (charts[a].createdAt||0));
    if (ids.length === 0) {
      writeCurrentChartId(null);
      set({ charts: {}, currentId: null, ...makeBlankChart(), screen: 'input' });
      return;
    }
    if (id === s.currentId) {
      set({ charts, currentId: null, ...makeBlankChart(), screen: 'input' });
      await get().switchChart(ids[0]);
      return;
    }
    set({ charts });
  },

  renameChart: (id, label) => set(s => ({
    charts: { ...s.charts, [id]: { ...s.charts[id], label } },
  })),

  logout: async () => {
    const { logout: logoutApi } = await import('../lib/api.js');
    void logoutApi().catch(() => { /* best effort */ });
    clearAuthSessionHint();
    clearAuthPhoneHint();
    clearSession();
    clearClientSessionStorage();
    // module 级缓存（hepan SWR）也得清 — 不然 "A 退出 → B 在同一浏览器
    // 登录 → B 点合盘按钮第一帧看到的是 A 的历史"，是隐私 + 正确性问题。
    // 用 dynamic import 避免循环依赖：useAppStore 启动期就被引；hepanApi
    // 不一定在那时候已经初始化。
    try {
      const { invalidateHepanMine } = await import('../lib/hepanApi.js');
      invalidateHepanMine();
    } catch { /* 静默 — logout 是 best-effort，没必要因为缓存清理失败而阻断 */ }
    try {
      const { clearBBirth } = await import('../lib/hepanBContext.js');
      clearBBirth();
    } catch { /* 同上 */ }
    set((state) => ({
      ...initialState,
      ...makeBlankChart(),
      charts: {},
      currentId: null,
      screen: 'landing',
      llmEnabled: state.llmEnabled,
      user: null,
    }));
  },

  // Snapshot current flat state back to charts[currentId] (called by persistence).
  commitCurrentChart: () => {
    const s = get();
    if (!s.currentId) return;
    set({
      charts: { ...s.charts, [s.currentId]: { ...s.charts[s.currentId], ...snapshotChart(s) } },
    });
  },

  // ── Session restore (v4) ──────────────────────────────────────────────────
  restoreFromSession: (saved) => {
    if (saved.version === SESSION_VERSION && saved.currentId && saved.charts?.[saved.currentId]) {
      const t = saved.charts[saved.currentId];
      set({
        charts: saved.charts,
        currentId: saved.currentId,
        screen: 'shell',
        paipan: t.paipan||null, force: t.force||[], guards: t.guards||[],
        dayun: t.dayun||[], meta: t.meta||null, birthInfo: t.birthInfo||null,
        sections: t.sections||[],
        // chat data: cleared; App.jsx will call loadConversations + loadMessages
        chatHistory: [], conversations: [], currentConversationId: null,
        gua: { current: null, history: [] },
        dayunCache: t.dayunCache||{}, liunianCache: t.liunianCache||{},
        verdicts: hydrateVerdicts(t.verdicts),
        classics: hydrateClassics(t.classics),
        dayunOpenIdx: null, liunianOpenKey: null,
      });
    }
  },

  // startNewChart: clear flat chart state + go to form, but KEEP all charts in memory
  startNewChart: () => set((state) => {
    const charts = state.currentId && state.charts[state.currentId]
      ? {
          ...state.charts,
          [state.currentId]: { ...state.charts[state.currentId], ...snapshotChart(state) },
        }
      : state.charts;
    return {
      ...makeBlankChart(),
      charts,
      currentId: null,
      screen: 'input',
      view: 'chart',
      dayunOpenIdx: null,
      liunianOpenKey: null,
      formError: null,
      sectionsLoading: false,
      sectionsError: null,
    };
  }),

  // reset: clear EVERYTHING (all charts + flat state), used for "× clear all"
  reset: () => set((state) => ({
    ...initialState,
    ...makeBlankChart(),
    charts: {},
    currentId: null,
    screen: 'input',
    llmEnabled: state.llmEnabled,
    user: state.user,
  })),
}));

// Dev-only：把 store 暴露到 window 上方便调试 / 自动化测试 — 比如自定义
// 触发一次 paywall toast 看渲染。生产构建里 import.meta.env.DEV === false，
// 这块整体被 dead-code-eliminate 掉。
if (import.meta.env?.DEV && typeof window !== 'undefined') {
  window.__baziStore = useAppStore;
}
