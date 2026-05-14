import test from 'node:test';
import assert from 'node:assert/strict';

import { useAppStore } from '../src/store/useAppStore.js';

function installStorage(seed = {}) {
  const data = { ...seed };
  const storage = {
    getItem: (key) => data[key] ?? null,
    setItem: (key, value) => { data[key] = String(value); },
    removeItem: (key) => { delete data[key]; },
    clear: () => { for (const key of Object.keys(data)) delete data[key]; },
  };
  globalThis.localStorage = storage;
  globalThis.window = { localStorage: storage };
  return data;
}

function resetStore() {
  useAppStore.setState({
    screen: 'landing',
    user: null,
    charts: {},
    currentId: null,
    paipan: null,
    meta: null,
  });
}

test.beforeEach(() => {
  installStorage();
  delete globalThis.fetch;
  resetStore();
});

test('landing CTA routes to auth when user is logged out', async () => {
  await useAppStore.getState().enterFromLanding();
  assert.equal(useAppStore.getState().screen, 'auth');
});

test('landing CTA routes to input when logged-in user has no charts', async () => {
  let syncCalls = 0;
  useAppStore.setState({
    user: { id: 'u1' },
    syncChartsFromServer: async () => {
      syncCalls += 1;
      return [];
    },
  });

  await useAppStore.getState().enterFromLanding();

  assert.equal(syncCalls, 1);
  assert.equal(useAppStore.getState().screen, 'input');
});

test('landing CTA recovers stale local session before routing to input', async () => {
  installStorage({
    'youshi:guest-token': 'staleguesttoken123456',
    authSessionHint: '1',
  });
  let syncCalls = 0;
  let guestCalls = 0;

  globalThis.fetch = async (url, options = {}) => {
    if (url === '/api/auth/guest') {
      guestCalls += 1;
      assert.equal(options.credentials, 'include');
      return {
        ok: true,
        json: async () => ({
          user: { id: 'fresh-guest' },
          guest_token: 'freshguesttoken123456',
        }),
      };
    }
    throw new Error(`unexpected fetch ${url}`);
  };

  useAppStore.setState({
    user: { id: 'stale-user' },
    syncChartsFromServer: async () => {
      syncCalls += 1;
      if (syncCalls === 1) {
        const error = new Error('登录状态已失效，请重新进入');
        error.status = 401;
        throw error;
      }
      return [];
    },
  });

  await useAppStore.getState().enterFromLanding();

  assert.equal(guestCalls, 1);
  assert.equal(syncCalls, 2);
  assert.equal(useAppStore.getState().user.id, 'fresh-guest');
  assert.equal(useAppStore.getState().screen, 'input');
  assert.equal(globalThis.localStorage.getItem('youshi:guest-token'), 'freshguesttoken123456');
});

test('landing CTA routes to shell using the latest loaded chart when charts are present', async () => {
  const calls = [];
  useAppStore.setState({
    user: { id: 'u1' },
    currentId: null,
    charts: {
      old: { id: 'old', createdAt: 1, paipan: { sizhu: { day: '甲子' } }, meta: { rizhu: '甲子' } },
      latest: { id: 'latest', createdAt: 2, paipan: { sizhu: { day: '乙丑' } }, meta: { rizhu: '乙丑' } },
    },
    switchChart: async (id) => {
      calls.push(id);
      useAppStore.setState({ currentId: id, screen: 'shell' });
    },
  });

  await useAppStore.getState().enterFromLanding();

  assert.deepEqual(calls, ['latest']);
  assert.equal(useAppStore.getState().screen, 'shell');
  assert.equal(useAppStore.getState().currentId, 'latest');
});
