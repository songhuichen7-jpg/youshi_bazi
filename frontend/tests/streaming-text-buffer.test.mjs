import test from 'node:test';
import assert from 'node:assert/strict';

import { createStreamingTextBuffer } from '../src/lib/streamingTextBuffer.js';

test('streaming text buffer coalesces rapid deltas into the latest frame text', () => {
  const seen = [];
  let scheduled = null;

  const buffer = createStreamingTextBuffer({
    onFlush: (text) => seen.push(text),
    schedule: (callback) => {
      scheduled = callback;
      return 'frame-1';
    },
    cancel: () => {},
  });

  buffer.push('你');
  buffer.push('你好');

  assert.deepEqual(seen, []);
  assert.equal(typeof scheduled, 'function');

  scheduled();

  assert.deepEqual(seen, ['你好']);
});

test('streaming text buffer flushes pending text immediately before done or abort', () => {
  const seen = [];
  const cancelled = [];

  const buffer = createStreamingTextBuffer({
    onFlush: (text) => seen.push(text),
    schedule: () => 'frame-1',
    cancel: (frameId) => cancelled.push(frameId),
  });

  buffer.push('半');
  buffer.push('半成品');
  buffer.flush();

  assert.deepEqual(seen, ['半成品']);
  assert.deepEqual(cancelled, ['frame-1']);
});
