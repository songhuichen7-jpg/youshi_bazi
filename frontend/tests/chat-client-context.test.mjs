import test from 'node:test';
import assert from 'node:assert/strict';

import { buildChatClientContext } from '../src/lib/chatClientContext.js';


test('buildChatClientContext includes current view focus and visible classics', () => {
  const context = buildChatClientContext({
    view: 'chart',
    workspace: { contextLabel: '2014 甲午' },
    classics: {
      status: 'done',
      items: [
        {
          source: '穷通宝鉴',
          scope: '论甲木 · 三秋甲木',
          quote: '七月甲木，丁火为尊，庚金次之。',
          plain: '七月甲木先看丁火，再看庚金。',
          match: '本盘甲木生申月，庚透而丁藏。',
        },
      ],
    },
  });

  assert.equal(context.view, 'chart');
  assert.equal(context.context_label, '2014 甲午');
  assert.equal(context.classics[0].source, '穷通宝鉴');
  assert.equal(context.classics[0].quote, '七月甲木，丁火为尊，庚金次之。');
  assert.equal(context.classics[0].match, '本盘甲木生申月，庚透而丁藏。');
});


test('buildChatClientContext no longer emits a hepan field', () => {
  const ctx = buildChatClientContext({ view: 'chart', workspace: {}, classics: { items: [] } });
  assert.equal('hepan' in ctx, false);
});


test('buildChatClientContext caps classics and trims long fields', () => {
  const items = Array.from({ length: 9 }, (_, index) => ({
    source: `书${index}`,
    scope: `卷${index}`,
    quote: '甲'.repeat(500),
    plain: '乙'.repeat(400),
    match: '丙'.repeat(400),
  }));

  const context = buildChatClientContext({
    view: 'classics',
    workspace: {},
    classics: { status: 'done', items },
  });

  assert.equal(context.classics.length, 6);
  assert.equal(context.classics[0].quote.length, 221);
  assert.equal(context.classics[0].plain.length, 181);
  assert.equal(context.classics[0].match.length, 181);
});
