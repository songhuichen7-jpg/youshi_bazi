import test from 'node:test';
import assert from 'node:assert/strict';

import { listCharts, createChart, deleteChart, fetchClassics } from '../src/lib/api.js';

function stubFetch(impl) {
  globalThis.fetch = impl;
}

function restoreFetch() {
  delete globalThis.fetch;
}

test('listCharts GETs /api/charts with credentials', async () => {
  let captured;
  stubFetch(async (url, opts) => {
    captured = { url, opts };
    return {
      ok: true,
      status: 200,
      json: async () => ({ items: [] }),
    };
  });

  try {
    const result = await listCharts();
    assert.equal(captured.url, '/api/charts');
    assert.equal(captured.opts.credentials, 'include');
    assert.deepEqual(result, { items: [] });
  } finally {
    restoreFetch();
  }
});

test('createChart POSTs chart create contract with credentials', async () => {
  let captured;
  stubFetch(async (url, opts) => {
    captured = { url, opts };
    return {
      ok: true,
      status: 201,
      json: async () => ({ chart: { id: 'chart-1', label: '测试盘' } }),
    };
  });

  try {
    const payload = {
      birth_input: {
        year: 1990,
        month: 5,
        day: 12,
        hour: 14,
        minute: 30,
        city: '北京',
        gender: 'male',
      },
      label: '测试盘',
    };
    const result = await createChart(payload);
    assert.equal(captured.url, '/api/charts');
    assert.equal(captured.opts.method, 'POST');
    assert.equal(captured.opts.credentials, 'include');
    assert.equal(captured.opts.body, JSON.stringify(payload));
    assert.equal(result.chart.id, 'chart-1');
  } finally {
    restoreFetch();
  }
});

test('deleteChart DELETEs /api/charts/:id with credentials', async () => {
  let captured;
  stubFetch(async (url, opts) => {
    captured = { url, opts };
    return { ok: true, status: 204 };
  });

  try {
    await deleteChart('chart-123');
    assert.equal(captured.url, '/api/charts/chart-123');
    assert.equal(captured.opts.method, 'DELETE');
    assert.equal(captured.opts.credentials, 'include');
  } finally {
    restoreFetch();
  }
});

test('fetchClassics GETs /api/charts/:id/classics with credentials', async () => {
  let captured;
  stubFetch(async (url, opts) => {
    captured = { url, opts };
    return {
      ok: true,
      status: 200,
      json: async () => ({ items: [{ source: '穷通宝鉴', scope: '甲木 · 寅月', chars: 12, text: '原文节选' }] }),
    };
  });

  try {
    const result = await fetchClassics('chart-123');
    assert.equal(captured.url, '/api/charts/chart-123/classics');
    assert.equal(captured.opts.credentials, 'include');
    assert.deepEqual(result.items[0], {
      source: '穷通宝鉴',
      scope: '甲木 · 寅月',
      chars: 12,
      text: '原文节选',
    });
  } finally {
    restoreFetch();
  }
});
