// frontend/tests/time-segment-picker.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { TIME_SEGMENTS } from '../src/components/card/timeSegments.js';

test('exports 6 time segments in correct order', () => {
  assert.equal(TIME_SEGMENTS.length, 6);
  assert.deepEqual(TIME_SEGMENTS.map(s => s.label), [
    '凌晨', '早上', '上午', '下午', '傍晚', '深夜',
  ]);
});

test('each segment has range and center hour', () => {
  for (const seg of TIME_SEGMENTS) {
    assert.ok(seg.range);
    assert.ok(typeof seg.hour === 'number');
    assert.ok(seg.hour >= 0 && seg.hour < 24);
  }
});

test('center hours fall cleanly inside 时辰 boundaries (not on edges)', () => {
  // 时辰 boundaries are odd hours 1,3,5,7,9,11,13,15,17,19,21,23
  // Center hours in our spec: 2, 6, 10, 14, 18, 22 — all even, fall cleanly in single 时辰
  const centers = TIME_SEGMENTS.map(s => s.hour);
  assert.deepEqual(centers, [2, 6, 10, 14, 18, 22]);
});
