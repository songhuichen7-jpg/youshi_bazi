import test from 'node:test';
import assert from 'node:assert/strict';

import { applyChatProgressEvent, createChatProgress } from '../src/lib/chatProgress.js';

test('createChatProgress starts empty so fast questions do not show invented steps', () => {
  const progress = createChatProgress({ contextLabel: '戊午大运', seed: 123 });

  assert.equal(progress.phase, 'idle');
  assert.equal(progress.intent, null);
  assert.equal(progress.hasRetrieval, false);
  assert.equal(progress.hasOutput, false);
  assert.equal(progress.seed, 123);
});

test('chat progress records intent and retrieval as state, not visible receipts', () => {
  let progress = createChatProgress();

  progress = applyChatProgressEvent(progress, {
    type: 'intent',
    intent: 'timing',
  });
  assert.equal(progress.phase, 'routing');
  assert.equal(progress.intent, 'timing');

  progress = applyChatProgressEvent(progress, {
    type: 'retrieval',
    source: '穷通宝鉴 · 三秋甲木 + 子平真诠·论用神',
  });
  assert.equal(progress.phase, 'streaming');
  assert.equal(progress.hasRetrieval, true);

  progress = applyChatProgressEvent(progress, {
    type: 'delta',
  });
  assert.equal(progress.phase, 'streaming');
  assert.equal(progress.hasOutput, true);
});

test('chat progress uses planner retrieval policy instead of intent hard-coding', () => {
  let progress = createChatProgress();

  progress = applyChatProgressEvent(progress, {
    type: 'intent',
    intent: 'media',
    needs: { classics: true },
    retrieval_plan: { enabled: true, focus: ['性情', '情绪模式'] },
  });

  assert.equal(progress.intent, 'media');
  assert.equal(progress.needsClassics, true);
  assert.deepEqual(progress.retrievalFocus, ['性情', '情绪模式']);
});

test('chat progress can record redirect and stop without inventing extra stages', () => {
  let progress = createChatProgress();
  progress = applyChatProgressEvent(progress, { type: 'redirect', to: 'gua' });
  progress = applyChatProgressEvent(progress, { type: 'abort' });

  assert.equal(progress.phase, 'stopped');
  assert.equal(progress.redirectTo, 'gua');
});

test('chat progress treats meta intent as state without surfacing copy', () => {
  let progress = createChatProgress();
  progress = applyChatProgressEvent(progress, { type: 'intent', intent: 'meta' });
  progress = applyChatProgressEvent(progress, { type: 'delta' });

  assert.equal(progress.phase, 'streaming');
  assert.equal(progress.intent, 'meta');
  assert.equal(progress.hasOutput, true);
});
