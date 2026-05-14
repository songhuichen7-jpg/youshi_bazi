import test from 'node:test';
import assert from 'node:assert/strict';

import { getConversationDisplayLabel } from '../src/lib/conversationDisplay.js';

// 给测试构造一个 stub getCached — items === null 表示 cache 还没拉到。
function withCachedItems(items, fn) {
  const getCached = () => (items === null ? null : { items });
  return fn(getCached);
}

test('returns explicit label when conversation has one', () => {
  const conv = { label: '我的随便起的名字', hepan_slug: 'abc' };
  withCachedItems(null, (getCached) => {
    assert.equal(getConversationDisplayLabel(conv, { getCached }), '我的随便起的名字');
  });
});

test('derives "合盘 · A × B" from cache when hepan_slug present and label is null', () => {
  const conv = { label: null, hepan_slug: 'abc' };
  withCachedItems([
    { slug: 'abc', a_nickname: '小夜灯', b_nickname: '多肉' },
  ], (getCached) => {
    assert.equal(getConversationDisplayLabel(conv, { getCached }), '合盘 · 小夜灯 × 多肉');
  });
});

test('falls back to cosmic_name when nickname missing', () => {
  const conv = { label: null, hepan_slug: 'abc' };
  withCachedItems([
    { slug: 'abc', a_nickname: null, a_cosmic_name: '橡子', b_cosmic_name: '含羞草' },
  ], (getCached) => {
    assert.equal(getConversationDisplayLabel(conv, { getCached }), '合盘 · 橡子 × 含羞草');
  });
});

test('returns "合盘对话" placeholder when hepan_slug present but cache miss', () => {
  const conv = { label: null, hepan_slug: 'abc' };
  withCachedItems([], (getCached) => {
    assert.equal(getConversationDisplayLabel(conv, { getCached }), '合盘对话');
  });
});

test('returns "合盘对话" when cache is null (not yet loaded)', () => {
  const conv = { label: null, hepan_slug: 'abc' };
  withCachedItems(null, (getCached) => {
    assert.equal(getConversationDisplayLabel(conv, { getCached }), '合盘对话');
  });
});

test('returns "新对话" when no label and no hepan_slug', () => {
  const conv = { label: null, hepan_slug: null };
  withCachedItems(null, (getCached) => {
    assert.equal(getConversationDisplayLabel(conv, { getCached }), '新对话');
  });
});

test('handles null/undefined conversation defensively', () => {
  withCachedItems(null, (getCached) => {
    assert.equal(getConversationDisplayLabel(null, { getCached }), '新对话');
    assert.equal(getConversationDisplayLabel(undefined, { getCached }), '新对话');
  });
});

test('treats whitespace-only label as empty (falls through to derive)', () => {
  const conv = { label: '   ', hepan_slug: 'abc' };
  withCachedItems([
    { slug: 'abc', a_nickname: '小夜灯', b_nickname: '多肉' },
  ], (getCached) => {
    assert.equal(getConversationDisplayLabel(conv, { getCached }), '合盘 · 小夜灯 × 多肉');
  });
});
