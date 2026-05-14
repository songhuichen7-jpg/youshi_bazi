import test from 'node:test';
import assert from 'node:assert/strict';

import { sendSmsCode, register, login, guestLogin, me } from '../src/lib/api.js';
import { useAppStore } from '../src/store/useAppStore.js';

function stubFetch(impl) {
  globalThis.fetch = impl;
}

function restoreFetch() {
  delete globalThis.fetch;
}

function resetStore() {
  useAppStore.setState({ user: null });
}

test.beforeEach(() => {
  resetStore();
});

test('sendSmsCode POSTs phone + purpose with credentials', async () => {
  let captured;
  stubFetch(async (url, opts) => {
    captured = { url, opts };
    return {
      ok: true,
      status: 200,
      json: async () => ({ expires_in: 300, __devCode: '123456' }),
    };
  });

  try {
    const result = await sendSmsCode('13800138001', 'register');
    assert.equal(captured.url, '/api/auth/sms/send');
    assert.equal(captured.opts.method, 'POST');
    assert.equal(captured.opts.credentials, 'include');
    assert.equal(
      captured.opts.body,
      JSON.stringify({ phone: '13800138001', purpose: 'register' }),
    );
    assert.equal(result.__devCode, '123456');
  } finally {
    restoreFetch();
  }
});

test('register returns user and store setUser keeps it', async () => {
  const user = { id: 'u-register', phone_last4: '8001', nickname: '测试' };
  stubFetch(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ user }),
  }));

  try {
    const result = await register({
      phone: '13800138001',
      code: '123456',
      invite_code: 'TESTING',
      nickname: '测试',
      agreed_to_terms: true,
    });
    useAppStore.getState().setUser(result.user);
    assert.deepEqual(useAppStore.getState().user, user);
  } finally {
    restoreFetch();
  }
});

test('login returns user and store setUser keeps it', async () => {
  const user = { id: 'u-login', phone_last4: '8001', nickname: null };
  stubFetch(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ user }),
  }));

  try {
    const result = await login({ phone: '13800138001', code: '654321' });
    useAppStore.getState().setUser(result.user);
    assert.deepEqual(useAppStore.getState().user, user);
  } finally {
    restoreFetch();
  }
});

test('guestLogin POSTs to guest auth endpoint with credentials', async () => {
  const user = { id: 'u-guest', phone_last4: '9527', nickname: '游客' };
  let captured;
  stubFetch(async (url, opts) => {
    captured = { url, opts };
    return {
      ok: true,
      status: 200,
      json: async () => ({ user }),
    };
  });

  try {
    const result = await guestLogin();
    assert.equal(captured.url, '/api/auth/guest');
    assert.equal(captured.opts.method, 'POST');
    assert.equal(captured.opts.credentials, 'include');
    assert.deepEqual(result.user, user);
  } finally {
    restoreFetch();
  }
});

test('me returns null on expected 401 bootstrap misses', async () => {
  stubFetch(async () => ({
    ok: false,
    status: 401,
    json: async () => ({ detail: { message: 'unauthorized' } }),
  }));

  try {
    const result = await me();
    assert.equal(result, null);
  } finally {
    restoreFetch();
  }
});
