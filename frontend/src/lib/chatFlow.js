export function finalizeChatTurn({ setChatStreaming }) {
  setChatStreaming(false);
}

export function shouldHydrateConversation({
  skipConversationHydration,
  conversationCreated,
  chatStreaming,
  guaStreaming,
}) {
  if (skipConversationHydration) {
    return { hydrate: false, clearSkip: true };
  }
  if (conversationCreated) {
    return { hydrate: false, clearSkip: false };
  }
  if (chatStreaming || guaStreaming) {
    return { hydrate: false, clearSkip: false };
  }
  return { hydrate: true, clearSkip: false };
}

function isOptimisticConversationId(value) {
  return String(value || '').startsWith('temp-conv-');
}

export async function resolveConversationIdForSend({
  currentConversationId,
  currentChartId,
  ensureConversation,
}) {
  if (!currentChartId || typeof ensureConversation !== 'function') return null;
  if (currentConversationId && !isOptimisticConversationId(currentConversationId)) {
    return currentConversationId;
  }
  const result = await ensureConversation(currentChartId);
  return result?.conversationId || null;
}
