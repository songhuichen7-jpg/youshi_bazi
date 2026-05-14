import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  __setAdminFetch,
  fetchAdminOperations,
  fetchAdminOverview,
  listAdminEvents,
  listAdminVisitors,
} from '../src/lib/adminApi.js';

test('admin API sends X-Admin-Token and date window', async () => {
  let captured;
  __setAdminFetch(async (url, opts) => {
    captured = { url, opts };
    return {
      ok: true,
      json: async () => ({ totals: {}, counts: {}, rates: {}, recent_events: [] }),
    };
  });

  await fetchAdminOverview({
    token: 'secret-token',
    from: '2026-05-01T00:00:00Z',
    to: '2026-05-02T00:00:00Z',
  });

  assert.match(captured.url, /\/api\/admin\/overview\?/);
  assert.match(captured.url, /from_=2026-05-01T00%3A00%3A00Z/);
  assert.equal(captured.opts.headers['X-Admin-Token'], 'secret-token');
});

test('admin list helpers build filters', async () => {
  const urls = [];
  __setAdminFetch(async (url) => {
    urls.push(url);
    return { ok: true, json: async () => ({ items: [] }) };
  });

  await listAdminVisitors({ token: 't', anonymousId: 'a_123' });
  await listAdminEvents({ token: 't', event: 'chat_error', anonymousId: 'a_123' });

  assert.match(urls[0], /anonymous_id=a_123/);
  assert.match(urls[1], /event=chat_error/);
  assert.match(urls[1], /anonymous_id=a_123/);
});

test('admin operations helper fetches token analytics', async () => {
  let captured;
  __setAdminFetch(async (url, opts) => {
    captured = { url, opts };
    return {
      ok: true,
      json: async () => ({
        tokens: { total: 0 },
        series: [],
        endpoint_breakdown: [],
        model_breakdown: [],
        top_users: [],
        funnel: [],
      }),
    };
  });

  const data = await fetchAdminOperations({
    token: 'ops-token',
    from: '2026-05-01T00:00:00Z',
    to: '2026-05-02T00:00:00Z',
  });

  assert.match(captured.url, /\/api\/admin\/operations\?/);
  assert.match(captured.url, /from_=2026-05-01T00%3A00%3A00Z/);
  assert.equal(captured.opts.headers['X-Admin-Token'], 'ops-token');
  assert.deepEqual(data.series, []);
});

test('App exposes the admin route', () => {
  const source = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8');
  assert.match(source, /path="\/admin"/);
});

test('visitor rows can drill into filtered event stream', () => {
  const source = readFileSync(new URL('../src/components/admin/AdminDashboard.jsx', import.meta.url), 'utf8');
  assert.match(source, /load\(\{ anonymousId: id \}\)/);
});

test('admin dashboard renders operations charts and token KPIs', () => {
  const source = readFileSync(new URL('../src/components/admin/AdminDashboard.jsx', import.meta.url), 'utf8');

  assert.match(source, /fetchAdminOperations/);
  assert.match(source, /Token 消耗趋势/);
  assert.match(source, /功能成本排行/);
  assert.match(source, /用户转化漏斗/);
  assert.match(source, /高消耗用户/);
  assert.match(source, /访问性能/);
  assert.match(source, /CHART_COLORS/);
});
