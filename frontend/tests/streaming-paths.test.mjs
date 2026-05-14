import test from 'node:test';
import assert from 'node:assert/strict';

import {
  streamSections,
  streamVerdicts,
  streamDayunStep,
  streamLiunian,
} from '../src/lib/api.js';

function makeSseResponse() {
  const enc = new TextEncoder();
  return {
    ok: true,
    status: 200,
    body: new ReadableStream({
      start(controller) {
        controller.enqueue(enc.encode('data: {"type":"done","full":"ok"}\n\n'));
        controller.close();
      },
    }),
  };
}

function stubFetch(impl) {
  globalThis.fetch = impl;
}

function restoreFetch() {
  delete globalThis.fetch;
}

test('streamSections hits chart-scoped SSE path with credentials', async () => {
  let captured;
  stubFetch(async (url, opts) => {
    captured = { url, opts };
    return makeSseResponse();
  });

  try {
    await streamSections('chart-1', { section: 'career' });
    assert.equal(captured.url, '/api/charts/chart-1/sections');
    assert.equal(captured.opts.credentials, 'include');
    assert.equal(captured.opts.body, JSON.stringify({ section: 'career' }));
  } finally {
    restoreFetch();
  }
});

test('streamVerdicts hits chart-scoped SSE path with credentials', async () => {
  let captured;
  stubFetch(async (url, opts) => {
    captured = { url, opts };
    return makeSseResponse();
  });

  try {
    await streamVerdicts('chart-1');
    assert.equal(captured.url, '/api/charts/chart-1/verdicts');
    assert.equal(captured.opts.credentials, 'include');
    assert.equal(captured.opts.body, undefined);
  } finally {
    restoreFetch();
  }
});

test('streamDayunStep hits chart-scoped SSE path with credentials', async () => {
  let captured;
  stubFetch(async (url, opts) => {
    captured = { url, opts };
    return makeSseResponse();
  });

  try {
    await streamDayunStep('chart-1', 3);
    assert.equal(captured.url, '/api/charts/chart-1/dayun/3');
    assert.equal(captured.opts.credentials, 'include');
    assert.equal(captured.opts.body, undefined);
  } finally {
    restoreFetch();
  }
});

test('streamLiunian hits chart-scoped SSE path with snake_case body and credentials', async () => {
  let captured;
  stubFetch(async (url, opts) => {
    captured = { url, opts };
    return makeSseResponse();
  });

  try {
    await streamLiunian('chart-1', { dayun_index: 2, year_index: 5 });
    assert.equal(captured.url, '/api/charts/chart-1/liunian');
    assert.equal(captured.opts.credentials, 'include');
    assert.equal(
      captured.opts.body,
      JSON.stringify({ dayun_index: 2, year_index: 5 }),
    );
  } finally {
    restoreFetch();
  }
});
