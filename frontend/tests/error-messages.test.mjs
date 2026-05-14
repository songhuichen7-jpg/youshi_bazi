import test from 'node:test';
import assert from 'node:assert/strict';

import { friendlyError } from '../src/lib/errorMessages.js';
import { loadSession, subscribeSave } from '../src/lib/persistence.js';

const originalLocalStorage = globalThis.localStorage;

function makeState(overrides = {}) {
  return {
    currentId: 'chart_a',
    charts: {
      chart_a: {
        id: 'chart_a',
        label: '测试命盘',
        createdAt: Date.now(),
      },
    },
    paipan: null,
    force: [],
    guards: [],
    dayun: [],
    meta: null,
    birthInfo: null,
    sections: [],
    chatHistory: [],
    dayunCache: {},
    liunianCache: {},
    gua: { current: null, history: [] },
    verdicts: { status: 'idle', picks: [], items: [], lastError: null },
    ...overrides,
  };
}

test.afterEach(() => {
  globalThis.localStorage = originalLocalStorage;
});

test('friendlyError classifies common user-facing failure types', () => {
  assert.deepEqual(
    friendlyError(new Error('Failed to fetch'), 'chat'),
    { title: '网络连接有点问题', detail: 'Failed to fetch', retryable: true }
  );

  assert.deepEqual(
    friendlyError(new Error('LLM 401: Invalid API Key'), 'sections'),
    { title: '服务暂时不可用', detail: 'LLM 401: Invalid API Key', retryable: false }
  );

  assert.deepEqual(
    friendlyError(new Error('deepseek_api_key not configured'), 'chat'),
    { title: '服务暂时不可用', detail: 'deepseek_api_key not configured', retryable: false }
  );

  assert.deepEqual(
    friendlyError(new Error('HTTP 429'), 'chat'),
    { title: '现在使用的人有点多', detail: 'HTTP 429', retryable: true }
  );

  assert.deepEqual(
    friendlyError(new Error('HTTP 503'), 'verdicts'),
    { title: '模型服务偶尔调皮', detail: 'HTTP 503', retryable: true }
  );

  assert.deepEqual(
    friendlyError(new Error('LLM returned no parseable sections'), 'sections'),
    { title: '这次 AI 没按规矩输出', detail: 'LLM returned no parseable sections', retryable: true }
  );

  assert.deepEqual(
    friendlyError(new Error('verdicts tree missing'), 'verdicts'),
    { title: '功能暂时不可用', detail: 'verdicts tree missing', retryable: false }
  );

  assert.deepEqual(
    friendlyError(new Error('wrong solar year 1800'), 'paipan'),
    { title: '请检查出生日期和城市', detail: 'wrong solar year 1800', retryable: false }
  );

  assert.deepEqual(
    friendlyError(new Error('QuotaExceededError: Failed to execute setItem on Storage'), 'storage_save'),
    { title: '浏览器存储空间不足', detail: 'QuotaExceededError: Failed to execute setItem on Storage', retryable: false }
  );

  assert.deepEqual(
    friendlyError(new Error('头像上传请求没有发出去，请检查网络后再试'), 'profile'),
    {
      title: '头像上传请求没有发出去，请检查网络后再试',
      detail: '',
      retryable: true,
    }
  );
});

test('loadSession reports unreadable local data through the notice callback', () => {
  const notices = [];
  globalThis.localStorage = {
    getItem() {
      return '{not-json';
    },
    removeItem() {},
  };

  const session = loadSession({ onError: (notice) => notices.push(notice) });

  assert.equal(session, null);
  assert.equal(notices.length, 1);
  assert.equal(notices[0].title, '本地记录读不出来了');
  assert.equal(notices[0].retryable, false);
});

test('subscribeSave keeps console warnings and emits a friendly storage notice when saving fails', () => {
  const notices = [];
  const warnings = [];
  let listener = null;
  const originalWarn = console.warn;
  console.warn = (...args) => warnings.push(args);

  globalThis.localStorage = {
    setItem() {
      throw new Error('QuotaExceededError');
    },
  };

  const fakeStore = {
    subscribe(fn) {
      listener = fn;
      return () => {};
    },
  };

  try {
    subscribeSave(fakeStore, { onError: (notice) => notices.push(notice) });
    listener(makeState());
  } finally {
    console.warn = originalWarn;
  }

  assert.ok(warnings.some((args) => args[0] === '[session] save failed:'));
  assert.equal(notices.length, 1);
  assert.equal(notices[0].title, '浏览器存储空间不足');
  assert.equal(notices[0].retryable, false);
});
