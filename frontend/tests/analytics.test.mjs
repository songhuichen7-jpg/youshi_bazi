import test from 'node:test';
import assert from 'node:assert/strict';
import { track, trackPagePerformance, trackPageView, __setTrackFetch } from '../src/lib/analytics.js';

test('track posts event with properties', async () => {
  let captured;
  __setTrackFetch(async (url, opts) => {
    captured = { url, body: JSON.parse(opts.body) };
    return { ok: true, status: 204 };
  });
  await track('card_view', { type_id: '01', from: 'direct' });
  assert.match(captured.url, /\/api\/track$/);
  assert.equal(captured.body.event, 'card_view');
  assert.equal(captured.body.properties.type_id, '01');
  assert.equal(captured.body.properties.from, 'direct');
});

test('track swallows network errors silently', async () => {
  __setTrackFetch(async () => { throw new Error('network down'); });
  await track('card_view', {});
  assert.ok(true);
});

test('track with no fetchImpl does nothing (no crash)', async () => {
  __setTrackFetch(null);
  await track('card_view', {});
  assert.ok(true);
});

test('trackPageView records route and page', async () => {
  let captured;
  __setTrackFetch(async (url, opts) => {
    captured = { url, body: JSON.parse(opts.body) };
    return { ok: true, status: 204 };
  });

  await trackPageView({ page: 'admin', route: '/admin' });

  assert.equal(captured.body.event, 'page_view');
  assert.equal(captured.body.properties.page, 'admin');
  assert.equal(captured.body.properties.route, '/admin');
});

test('trackPagePerformance records timing and transfer metrics', async () => {
  let captured;
  __setTrackFetch(async (url, opts) => {
    captured = { url, body: JSON.parse(opts.body) };
    return { ok: true, status: 204 };
  });

  await trackPagePerformance({
    page: 'landing',
    route: '/',
    metrics: {
      load_ms: 1234,
      ttfb_ms: 210,
      transfer_size: 456789,
      resource_count: 12,
    },
  });

  assert.equal(captured.body.event, 'page_performance');
  assert.equal(captured.body.properties.route, '/');
  assert.equal(captured.body.properties.load_ms, 1234);
  assert.equal(captured.body.properties.transfer_size, 456789);
});
