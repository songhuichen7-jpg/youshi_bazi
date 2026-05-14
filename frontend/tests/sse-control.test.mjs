import test from 'node:test';
import assert from 'node:assert/strict';

import { streamMessage, streamSSE } from '../src/lib/api.js';

function stubFetch(impl) {
  globalThis.fetch = impl;
}

function restoreFetch() {
  delete globalThis.fetch;
}

function makeSseResponse(blocks) {
  const enc = new TextEncoder();
  return {
    ok: true,
    status: 200,
    body: new ReadableStream({
      start(controller) {
        for (const block of blocks) controller.enqueue(enc.encode(block));
        controller.close();
      },
    }),
  };
}

test('streamSSE forwards AbortSignal and surfaces progress handlers', async () => {
  const controller = new AbortController();
  let captured;
  const seen = [];

  stubFetch(async (url, opts) => {
    captured = { url, opts };
    return makeSseResponse([
      'data: {"type":"intent","intent":"timing","reason":"focus_years","source":"rule","needs":{"classics":true},"retrieval_plan":{"enabled":true,"focus":["行运"]}}\n\n',
      'data: {"type":"retrieval","source":"穷通宝鉴 · 三秋甲木 + 子平真诠·论用神"}\n\n',
      'data: {"type":"model","modelUsed":"gpt-test"}\n\n',
      'data: {"type":"delta","text":"你"}\n\n',
      'data: {"type":"done","full":"你好"}\n\n',
    ]);
  });

  try {
    const full = await streamSSE('/api/mock', { q: 'hi' }, {
      signal: controller.signal,
      onIntent: (intent, _reason, _source, plan) => seen.push(['intent', intent, plan.needs.classics, plan.retrieval_plan.focus[0]]),
      onRetrieval: (source) => seen.push(['retrieval', source]),
      onModel: (model) => seen.push(['model', model]),
      onDelta: (_text, running) => seen.push(['delta', running]),
    });

    assert.equal(captured.opts.signal, controller.signal);
    assert.equal(full, '你好');
    assert.deepEqual(seen, [
      ['intent', 'timing', true, '行运'],
      ['retrieval', '穷通宝鉴 · 三秋甲木 + 子平真诠·论用神'],
      ['model', 'gpt-test'],
      ['delta', '你'],
    ]);
  } finally {
    restoreFetch();
  }
});

test('streamMessage passes AbortSignal through to conversation SSE request', async () => {
  const controller = new AbortController();
  let captured;

  stubFetch(async (url, opts) => {
    captured = { url, opts };
    return makeSseResponse([
      'data: {"type":"done","full":"ok"}\n\n',
    ]);
  });

  try {
    await streamMessage('conv-1', { message: '你好' }, { signal: controller.signal });
    assert.equal(captured.url, '/api/conversations/conv-1/messages');
    assert.equal(captured.opts.signal, controller.signal);
  } finally {
    restoreFetch();
  }
});
