import test from 'node:test';
import assert from 'node:assert/strict';

import {
  FORBIDDEN_THINKING_PATTERNS,
  THINKING_COPY_POOLS,
  buildThinkingSequence,
} from '../src/lib/chatThinking.js';


test('thinking copy pools avoid awkward support-agent wording', () => {
  const allLines = Object.values(THINKING_COPY_POOLS).flat();
  assert.ok(allLines.length >= 70);

  for (const line of allLines) {
    for (const pattern of FORBIDDEN_THINKING_PATTERNS) {
      assert.doesNotMatch(line, pattern, line);
    }
  }
});


test('buildThinkingSequence uses classics-aware copy when classics are visible', () => {
  const lines = buildThinkingSequence({
    intent: 'career',
    hasClassics: true,
    seed: 3,
  });

  assert.equal(lines.length, 3);
  assert.equal(new Set(lines).size, 3);
  assert.ok(lines.some((line) => /古籍|原文|古书|旁证/.test(line)));
});


test('buildThinkingSequence keeps chitchat light and non-divinatory', () => {
  const lines = buildThinkingSequence({
    intent: 'chitchat',
    hasClassics: true,
    seed: 8,
  });

  assert.equal(lines.length, 3);
  for (const line of lines) {
    assert.doesNotMatch(line, /命盘|古籍|干支|十神|大运|流年/);
    assert.doesNotMatch(line, /正在回复/);
  }
});


test('buildThinkingSequence avoids repeating the previous first line', () => {
  const first = buildThinkingSequence({ intent: 'wealth', seed: 2 })[0];
  const next = buildThinkingSequence({ intent: 'wealth', seed: 2, previousFirst: first });

  assert.notEqual(next[0], first);
});
