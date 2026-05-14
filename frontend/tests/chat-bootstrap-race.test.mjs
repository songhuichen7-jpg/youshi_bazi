import test from 'node:test';
import assert from 'node:assert/strict';

import * as chatFlow from '../src/lib/chatFlow.js';

test('bootstrap chips skip empty conversations so the first send can start immediately', async () => {
  assert.equal(typeof chatFlow.startBootstrapChipsRefresh, 'function');

  let refreshCalled = false;

  const refreshChips = async () => {
    refreshCalled = true;
    await new Promise((resolve) => setTimeout(resolve, 5000));
  };

  const bootstrapped = chatFlow.startBootstrapChipsRefresh({
    meta: { chart_id: 'chart-1' },
    currentConversationId: 'conv-1',
    historyLength: 0,
    refreshChips,
  });

  assert.equal(bootstrapped, false);
  assert.equal(refreshCalled, false);
});

test('send path reuses the current conversation id instead of waiting for bootstrap hydration', async () => {
  assert.equal(typeof chatFlow.resolveConversationIdForSend, 'function');

  let ensureCalls = 0;
  const convId = await chatFlow.resolveConversationIdForSend({
    currentConversationId: 'conv-existing',
    currentChartId: 'chart-1',
    ensureConversation: async () => {
      ensureCalls += 1;
      await new Promise((resolve) => setTimeout(resolve, 5000));
      return { conversationId: 'conv-from-bootstrap' };
    },
  });

  assert.equal(convId, 'conv-existing');
  assert.equal(ensureCalls, 0);
});

test('conversation hydration waits while chat stream owns the optimistic assistant slot', () => {
  assert.equal(typeof chatFlow.shouldHydrateConversation, 'function');

  assert.deepEqual(
    chatFlow.shouldHydrateConversation({
      skipConversationHydration: false,
      conversationCreated: false,
      chatStreaming: true,
      guaStreaming: false,
    }),
    { hydrate: false, clearSkip: false },
  );

  assert.deepEqual(
    chatFlow.shouldHydrateConversation({
      skipConversationHydration: false,
      conversationCreated: false,
      chatStreaming: false,
      guaStreaming: false,
    }),
    { hydrate: true, clearSkip: false },
  );
});

test('conversation hydration still consumes the one-shot chart creation skip flag', () => {
  assert.deepEqual(
    chatFlow.shouldHydrateConversation({
      skipConversationHydration: true,
      conversationCreated: false,
      chatStreaming: true,
      guaStreaming: false,
    }),
    { hydrate: false, clearSkip: true },
  );
});
