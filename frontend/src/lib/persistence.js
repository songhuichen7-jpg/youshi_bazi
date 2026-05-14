import { STORAGE_KEY, SESSION_VERSION } from './constants.js';
import { friendlyError } from './errorMessages.js';

export function loadSession(options = {}) {
  const onError = options.onError;
  try {
    const s = localStorage.getItem(STORAGE_KEY);
    if (!s) return null;
    const parsed = JSON.parse(s);

    // v1 → v3: discard (too old)
    if (parsed.version === 1) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }

    // v2 → v3: wrap flat data into a single chart entry
    if (parsed.version === 2) {
      if (!parsed.serverData?.PAIPAN) return null; // no chart data worth migrating
      const id = 'chart_' + (parsed.savedAt || Date.now());
      const label = (() => {
        const b = parsed.birthInfo;
        if (!b) return '已迁移命盘';
        const g = b.gender === 'female' ? '女' : '男';
        return `${g} · ${b.date || ''}${b.time ? ' ' + b.time : ''}`;
      })();
      const chart = {
        id, label,
        createdAt: parsed.savedAt || Date.now(),
        formData: parsed.birthInfo || null,
        paipan:  parsed.serverData?.PAIPAN || null,
        force:   parsed.serverData?.FORCE  || [],
        guards:  parsed.serverData?.GUARDS || [],
        dayun:   parsed.serverData?.DAYUN  || [],
        meta:    parsed.serverData?.META   || null,
        birthInfo: parsed.birthInfo || null,
        sections:     parsed.sections || [],
        chatHistory:  parsed.chatHistory || [],
        dayunCache:   parsed.dayunCache  || {},
        liunianCache: parsed.liunianCache || {},
        gua:          parsed.gua || { current: null, history: [] },
        verdicts:     parsed.verdicts,
      };
      return { version: SESSION_VERSION, currentId: id, charts: { [id]: chart } };
    }

    // v3 → v4: drop per-chart chat fields (now server-backed)
    if (parsed.version === 3) {
      const charts = {};
      for (const [id, c] of Object.entries(parsed.charts || {})) {
        const { chatHistory: _ch, conversations: _convs, currentConversationId: _cid, gua: _gua, ...rest } = c;
        charts[id] = rest;
      }
      return { version: SESSION_VERSION, currentId: parsed.currentId, charts };
    }

    // v4 native
    if (parsed.version === SESSION_VERSION) return parsed;

    // Unknown future version
    localStorage.removeItem(STORAGE_KEY);
    return null;
  } catch (e) {
    console.warn('[session] parse failed, clearing:', e.message || e);
    onError?.(friendlyError(e, 'storage_load'));
    try { localStorage.removeItem(STORAGE_KEY); } catch {
      // Ignore storage cleanup failures after a parse error.
    }
    return null;
  }
}

export function clearSession(options = {}) {
  try { localStorage.removeItem(STORAGE_KEY); } catch (e) {
    console.warn('[session] clear failed:', e.message || e);
    options.onError?.(friendlyError(e, 'storage_clear'));
  }
}

/**
 * Subscribe to store changes and persist v3 snapshot on every relevant update.
 * Commits current flat state back to charts[currentId] before saving.
 */
export function subscribeSave(store, options = {}) {
  const onError = options.onError;
  let lastJson = '';
  let lastNoticeKey = '';
  return store.subscribe((state) => {
    if (!state.currentId) return;
    // Merge current flat state into charts map before persisting
    const currentEntry = state.charts[state.currentId];
    if (!currentEntry) return;
    const merged = {
      ...currentEntry,
      paipan: state.paipan, force: state.force, guards: state.guards,
      dayun: state.dayun, meta: state.meta, birthInfo: state.birthInfo,
      sections: state.sections,
      dayunCache: state.dayunCache, liunianCache: state.liunianCache,
      verdicts: state.verdicts,
    };
    const charts = { ...state.charts, [state.currentId]: merged };
    const snap = {
      version: SESSION_VERSION,
      currentId: state.currentId,
      charts,
      savedAt: Date.now(),
    };
    const json = JSON.stringify(snap);
    if (json === lastJson) return;
    lastJson = json;
    try { localStorage.setItem(STORAGE_KEY, json); }
    catch (e) {
      console.warn('[session] save failed:', e.message || e);
      const notice = friendlyError(e, 'storage_save');
      const noticeKey = `${notice.title}|${notice.detail}`;
      if (noticeKey !== lastNoticeKey) {
        lastNoticeKey = noticeKey;
        onError?.(notice);
      }
    }
  });
}
