import { CHAT_HISTORY_MAX } from './constants.js';

let lastTruncateLogAt = 0;

function isPinnedChatMessage(message) {
  return message?.role === 'system' || message?.pinned === true || message?.kind === 'greeting' || message?.meta?.preserveOnTrim === true;
}

function logTruncation(max, logger = console) {
  const now = Date.now();
  if (now - lastTruncateLogAt < 100) return;
  lastTruncateLogAt = now;
  logger?.info?.('[chat] history truncated to', max);
}

export function trimChatHistory(history, { max = CHAT_HISTORY_MAX, logger = console } = {}) {
  const list = Array.isArray(history) ? history.slice() : [];
  if (list.length <= max) return list;

  const trimmed = max > 0 && isPinnedChatMessage(list[0])
    ? [list[0], ...list.slice(-(max - 1))]
    : list.slice(-max);

  logTruncation(max, logger);
  return trimmed;
}

export function appendChatMessage(history, message, options = {}) {
  return trimChatHistory([...(Array.isArray(history) ? history : []), message], options);
}
