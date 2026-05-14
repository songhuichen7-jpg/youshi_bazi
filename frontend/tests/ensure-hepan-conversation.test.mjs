import test from 'node:test';
import assert from 'node:assert/strict';
import { useAppStore } from '../src/store/useAppStore.js';

// sessionStorage shim for node — mirrors useAppStore.test.mjs setup
function _sessionStorageShim() {
  const data = {};
  globalThis.sessionStorage = {
    getItem: (k) => data[k] ?? null,
    setItem: (k, v) => { data[k] = String(v); },
    removeItem: (k) => { delete data[k]; },
    clear: () => { for (const k of Object.keys(data)) delete data[k]; },
  };
}

function reset() {
  _sessionStorageShim();
  useAppStore.setState({
    conversations: [],
    currentConversationId: null,
    chatHistory: [],
  });
}

test('ensureHepanConversation returns existing match without API', async () => {
  reset();
  useAppStore.setState({
    conversations: [
      { id: 'c1', chart_id: 'chart-1', hepan_slug: 'abc', deleted_at: null },
      { id: 'c2', chart_id: 'chart-1', hepan_slug: null,  deleted_at: null },
    ],
  });
  let called = false;
  global.fetch = async () => { called = true; return new Response('{}', { status: 200 }); };
  const id = await useAppStore.getState().ensureHepanConversation('chart-1', 'abc');
  assert.equal(id, 'c1');
  assert.equal(called, false);
  assert.equal(useAppStore.getState().currentConversationId, 'c1');
});

test('ensureHepanConversation creates a new conversation when none matches', async () => {
  reset();
  useAppStore.setState({
    conversations: [{ id: 'c1', chart_id: 'chart-1', hepan_slug: null, deleted_at: null }],
  });
  let captured = null;
  global.fetch = async (url, init) => {
    captured = { url: String(url), body: JSON.parse(init.body) };
    return new Response(JSON.stringify({
      id: 'c-new', chart_id: 'chart-1', label: null, hepan_slug: 'newslug',
      position: 1, created_at: '2026-05-07T00:00:00Z',
      updated_at: '2026-05-07T00:00:00Z', last_message_at: null,
      message_count: 0, deleted_at: null,
    }), { status: 200 });
  };
  const id = await useAppStore.getState().ensureHepanConversation('chart-1', 'newslug');
  assert.equal(id, 'c-new');
  // Body should NOT contain a label key (live-derived in UI now)
  assert.deepEqual(captured.body, { hepan_slug: 'newslug' });
  assert.ok(captured.url.includes('/api/charts/chart-1/conversations'));
  const state = useAppStore.getState();
  assert.equal(state.currentConversationId, 'c-new');
  assert.equal(state.conversations.length, 2);
  assert.equal(state.chatHistory.length, 0);
});

test('ensureHepanConversation rejects missing args', async () => {
  reset();
  await assert.rejects(useAppStore.getState().ensureHepanConversation('', 'abc'));
  await assert.rejects(useAppStore.getState().ensureHepanConversation('chart-1', ''));
});
