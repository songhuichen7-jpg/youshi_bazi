import test from 'node:test';
import assert from 'node:assert/strict';

import { CLASSICS_VERSION, useAppStore } from '../src/store/useAppStore.js';
import { SESSION_VERSION } from '../src/lib/constants.js';


function _stubFetch(impl) {
  globalThis.fetch = impl;
}
function _restoreFetch() { delete globalThis.fetch; }


// sessionStorage shim for node
function _sessionStorageShim() {
  const data = {};
  globalThis.sessionStorage = {
    getItem: (k) => data[k] ?? null,
    setItem: (k, v) => { data[k] = String(v); },
    removeItem: (k) => { delete data[k]; },
    clear: () => { for (const k of Object.keys(data)) delete data[k]; },
  };
}


function _resetStore() {
  useAppStore.setState({
    chatHistory: [], conversations: [], currentConversationId: null,
    currentId: 'chart-1',
  });
}


test('appendMessage adds to chatHistory ephemerally', () => {
  _resetStore();
  useAppStore.getState().appendMessage({ role: 'user', content: 'hi' });
  const [message] = useAppStore.getState().chatHistory;
  assert.equal(message.role, 'user');
  assert.equal(message.content, 'hi');
  assert.equal(typeof message.ts, 'number');
});


test('replaceLastAssistant updates only the last assistant', () => {
  useAppStore.setState({
    chatHistory: [
      { role: 'user', content: 'a' },
      { role: 'assistant', content: '' },
    ],
    currentId: 'chart-1', conversations: [], currentConversationId: null,
  });
  useAppStore.getState().replaceLastAssistant('done');
  assert.equal(useAppStore.getState().chatHistory[1].content, 'done');
});


test('prepareChatRegeneration trims later turns and opens a fresh assistant response', () => {
  useAppStore.setState({
    chatHistory: [
      { role: 'user', content: '原来的问题' },
      { role: 'assistant', content: '原来的回答' },
      { role: 'user', content: '后面的问题' },
      { role: 'assistant', content: '后面的回答' },
    ],
    currentId: 'chart-1', conversations: [], currentConversationId: null,
  });

  useAppStore.getState().prepareChatRegeneration(0, '改过的问题');

  assert.deepEqual(useAppStore.getState().chatHistory, [
    { role: 'user', content: '改过的问题' },
    { role: 'assistant', content: '' },
  ]);
});


test('replacePlaceholderWithCta turns last assistant into cta', () => {
  useAppStore.setState({
    chatHistory: [
      { role: 'user', content: '该不该' },
      { role: 'assistant', content: '' },
    ],
    currentId: 'chart-1', conversations: [], currentConversationId: null,
  });
  useAppStore.getState().replacePlaceholderWithCta('该不该', false);
  assert.deepEqual(useAppStore.getState().chatHistory[1], {
    role: 'cta', content: { question: '该不该', manual: false },
  });
});


test('consumeCta removes the trailing cta', () => {
  useAppStore.setState({
    chatHistory: [
      { role: 'user', content: 'q' },
      { role: 'cta', content: { question: 'q', manual: false } },
    ],
    currentId: 'chart-1', conversations: [], currentConversationId: null,
  });
  useAppStore.getState().consumeCta();
  const hist = useAppStore.getState().chatHistory;
  assert.equal(hist.length, 1);
  assert.equal(hist[0].role, 'user');
});


test('loadConversations populates store + picks first as default', async () => {
  _sessionStorageShim();
  _stubFetch(async () => ({ ok: true, json: async () => ({
    items: [{ id: 'c1', label: '对话 1' }, { id: 'c2', label: '对话 2' }],
  }) }));
  try {
    _resetStore();
    await useAppStore.getState().loadConversations('chart-1');
    const s = useAppStore.getState();
    assert.deepEqual(s.conversations.map(c => c.id), ['c1', 'c2']);
    assert.equal(s.currentConversationId, 'c1');
  } finally {
    _restoreFetch();
  }
});


test('loadConversations restores currentConversationId from sessionStorage', async () => {
  _sessionStorageShim();
  globalThis.sessionStorage.setItem('currentConversationId:chart-1', 'c2');
  _stubFetch(async () => ({ ok: true, json: async () => ({
    items: [{ id: 'c1' }, { id: 'c2' }],
  }) }));
  try {
    _resetStore();
    await useAppStore.getState().loadConversations('chart-1');
    assert.equal(useAppStore.getState().currentConversationId, 'c2');
  } finally {
    _restoreFetch();
    globalThis.sessionStorage.clear();
  }
});


test('loadMessages reverses server-newest-first to chronological', async () => {
  _sessionStorageShim();
  _stubFetch(async () => ({ ok: true, json: async () => ({
    items: [
      { id: '3', role: 'assistant', content: 'a2', meta: null, created_at: '2026-04-18T03:00:00Z' },
      { id: '2', role: 'user',      content: 'q2', meta: null, created_at: '2026-04-18T02:00:00Z' },
      { id: '1', role: 'user',      content: 'q1', meta: null, created_at: '2026-04-18T01:00:00Z' },
    ],
    next_cursor: null,
  }) }));
  try {
    _resetStore();
    await useAppStore.getState().loadMessages('c1');
    const hist = useAppStore.getState().chatHistory;
    assert.deepEqual(hist.map(m => m.content), ['q1', 'q2', 'a2']);
  } finally {
    _restoreFetch();
  }
});


test('newConversationOnServer appends + selects + clears history', async () => {
  _sessionStorageShim();
  _stubFetch(async () => ({ ok: true, status: 201, json: async () => ({
    id: 'cN', label: '对话 1',
  }) }));
  try {
    useAppStore.setState({ conversations: [], chatHistory: [{ role: 'user', content: 'old' }],
                            currentId: 'chart-1' });
    await useAppStore.getState().newConversationOnServer('chart-1', '对话 1');
    const s = useAppStore.getState();
    assert.equal(s.currentConversationId, 'cN');
    assert.deepEqual(s.chatHistory, []);
  } finally {
    _restoreFetch();
  }
});

test('newConversationOnServer switches immediately before the server response resolves', async () => {
  _sessionStorageShim();
  let resolveFetch;
  _stubFetch(async () => new Promise((resolve) => {
    resolveFetch = () => resolve({
      ok: true,
      status: 201,
      json: async () => ({ id: 'cN', label: '对话 2', chart_id: 'chart-1', position: 1 }),
    });
  }));

  try {
    useAppStore.setState({
      conversations: [{ id: 'c1', label: '对话 1', chart_id: 'chart-1', position: 0 }],
      currentConversationId: 'c1',
      chatHistory: [{ role: 'user', content: 'old' }],
      currentId: 'chart-1',
    });

    const pending = useAppStore.getState().newConversationOnServer('chart-1', '对话 2');
    const optimistic = useAppStore.getState();

    assert.equal(optimistic.chatHistory.length, 0);
    assert.equal(optimistic.conversations.length, 2);
    assert.equal(optimistic.conversations[1].label, '对话 2');
    assert.notEqual(optimistic.currentConversationId, 'c1');
    assert.match(String(optimistic.currentConversationId), /^temp-conv-/);

    for (let attempt = 0; attempt < 5 && typeof resolveFetch !== 'function'; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
    assert.equal(typeof resolveFetch, 'function');
    resolveFetch();
    await pending;

    const settled = useAppStore.getState();
    assert.equal(settled.currentConversationId, 'cN');
    assert.equal(settled.conversations[1].id, 'cN');
  } finally {
    _restoreFetch();
  }
});

test('loadClassics populates persona + verdict for the active chart', async () => {
  const personaPayload = {
    quote: '甲子日元，生于孟春。',
    plain: '木火得位，五行中和。',
    book: '滴天髓',
    chapter: '性情',
    section: '命例 1',
    tier: 'case',
    fit_note: '日干甲、月令寅、建禄当令。',
  };
  const verdictPayload = {
    quote: '正官透干、印星护身者，主清贵',
    book: '三命通会',
    chapter: '论命格高低',
  };
  _stubFetch(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ persona: personaPayload, verdict: verdictPayload }),
  }));

  try {
    useAppStore.setState({
      currentId: 'chart-1',
      charts: {
        'chart-1': {
          id: 'chart-1',
          classics: {
            status: 'idle', persona: null, verdict: null,
            lastError: null, version: CLASSICS_VERSION,
          },
        },
      },
    });
    await useAppStore.getState().loadClassics('chart-1');
    const state = useAppStore.getState();
    assert.equal(state.classics.status, 'done');
    assert.equal(state.classics.version, CLASSICS_VERSION);
    assert.deepEqual(state.classics.persona, personaPayload);
    assert.deepEqual(state.classics.verdict, verdictPayload);
    assert.equal(state.charts['chart-1'].classics.version, CLASSICS_VERSION);
    assert.deepEqual(state.charts['chart-1'].classics.persona, personaPayload);
    assert.deepEqual(state.charts['chart-1'].classics.verdict, verdictPayload);
  } finally {
    _restoreFetch();
  }
});

test('restoreFromSession discards stale classics cache before refetch', () => {
  useAppStore.setState(useAppStore.getInitialState(), true);

  useAppStore.getState().restoreFromSession({
    version: SESSION_VERSION,
    currentId: 'chart-1',
    charts: {
      'chart-1': {
        id: 'chart-1',
        paipan: { ok: true },
        meta: { ok: true },
        classics: {
          status: 'done',
          version: 'skill-index-v6',
          persona: { quote: '旧 persona', book: '旧书' },
          verdict: { quote: '旧 verdict', book: '旧书' },
          lastError: null,
        },
      },
    },
  });

  const state = useAppStore.getState();
  // Stale-version classics cache is dropped: version reset to current,
  // status back to idle, and persona/verdict cleared.
  assert.equal(state.classics.version, CLASSICS_VERSION);
  assert.equal(state.classics.status, 'idle');
  assert.equal(state.classics.persona, null);
  assert.equal(state.classics.verdict, null);
});

test('store starts with optimistic llmEnabled to avoid false fallback before health probe resolves', () => {
  assert.equal(useAppStore.getInitialState().llmEnabled, true);
});
