import { prepareAvatarUpload } from './avatarUpload.js';

/**
 * SSE streamer. Handlers: { onDelta(text, running), onDone(full, finishReason),
 *   onModel(m), onIntent(i,r,s), onThinking(chunk, running) }
 * Returns the final text. Thinking is streamed but not part of the returned
 * answer text (it's the model's internal reasoning, not the answer).
 *
 * finishReason: "stop"（正常结束）/ "length"（被 max_tokens 截断）/ null。前端
 * 据此显示截断警示 + 续写按钮，避免 partial 内容被悄悄当作完整回答。
 */
export async function streamSSE(url, body, handlers = {}) {
  const resp = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: body == null ? undefined : JSON.stringify(body),
    signal: handlers.signal,
  });
  if (!resp.ok || !resp.body) {
    throw await _errorFromResponse(resp);
  }
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let carry = '';
  let full = '';
  // Thinking 是模型的推演过程，跟答案分开累加。不计入 full 的返回值 — 调用方
  // 想看 thinking 通过 onThinking handler 拿。
  let thinkingFull = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    carry += dec.decode(value, { stream: true });
    const parts = carry.split('\n\n');
    carry = parts.pop() || '';
    for (const block of parts) {
      const line = block.trim();
      if (!line.startsWith('data:')) continue;
      let ev;
      try { ev = JSON.parse(line.slice(5).trim()); } catch { continue; }
      if (ev.type === 'delta' && ev.text) { full += ev.text; handlers.onDelta?.(ev.text, full); }
      else if (ev.type === 'thinking' && ev.text) { thinkingFull += ev.text; handlers.onThinking?.(ev.text, thinkingFull); }
      else if (ev.type === 'done') { if (ev.full) full = ev.full; handlers.onDone?.(full, ev.finish_reason || null); }
      else if (ev.type === 'model') handlers.onModel?.(ev.modelUsed);
      else if (ev.type === 'intent') handlers.onIntent?.(ev.intent, ev.reason, ev.source, ev);
      else if (ev.type === 'retrieval') handlers.onRetrieval?.(ev.source);
      else if (ev.type === 'suggestions') handlers.onSuggestions?.(ev.items);
      else if (ev.type === 'gua') handlers.onGua?.(ev.data);
      else if (ev.type === 'redirect') handlers.onRedirect?.(ev.to, ev.question);
      else if (ev.type === 'error') {
        // 后端 sse_pack({type:'error', code:'QUOTA_EXCEEDED', message:...}) 的
        // code 字段以前直接被扔掉，friendlyError 看不到 code 就匹配不到
        // paywall CTA。给 Error 挂上 friendlyError 期望的 payload 结构
        // (detail.code/message/details)，跟 HTTP 429 的形态对齐 — 这样
        // tryQuotaExceeded() 能跑、PLAN_UPGRADE_REQUIRED / QUOTA_EXCEEDED /
        // CHART_LIMIT_EXCEEDED 流式触发时也能正确弹 paywall。
        const errMsg = typeof ev.message === 'string' && ev.message
          ? ev.message
          : 'LLM error';
        const sseError = new Error(errMsg);
        if (ev.code) {
          sseError.payload = {
            detail: {
              code: ev.code,
              message: errMsg,
              details: ev.details || {},
            },
          };
          // status 留空 — friendlyError 头部按 status 拦的是 401/403/etc，
          // SSE error 没有 HTTP status，依靠 payload.detail.code 走分支
        }
        throw sseError;
      }
    }
  }
  return full;
}

async function _errorFromResponse(response) {
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  const message =
    payload?.detail?.message ||
    payload?.error?.message ||
    payload?.error ||
    payload?.message ||
    ('HTTP ' + response.status);
  const error = new Error(message);
  error.status = response.status;
  error.payload = payload;
  return error;
}

async function _getJSON(url) {
  const r = await fetch(url, { credentials: 'include' });
  if (!r.ok) throw await _errorFromResponse(r);
  return r.json();
}

async function _postJSON(url, body) {
  const r = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: body == null ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw await _errorFromResponse(r);
  return r.json();
}

async function _patchJSON(url, body) {
  const r = await fetch(url, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw await _errorFromResponse(r);
  return r.json();
}

async function _delete(url) {
  const r = await fetch(url, { method: 'DELETE', credentials: 'include' });
  if (!r.ok && r.status !== 204) throw await _errorFromResponse(r);
}

function parseSectionsText(raw) {
  if (!raw) return [];
  const firstMark = raw.search(/§\s*\d/);
  if (firstMark < 0) return [];
  const parts = raw.slice(firstMark).split(/§\s*(\d+)\s*/).filter(Boolean);
  const sections = [];
  for (let index = 0; index < parts.length - 1; index += 2) {
    const chunk = String(parts[index + 1] || '').trim();
    if (!chunk) continue;
    const lines = chunk.split('\n');
    const title = String(lines.shift() || '').trim();
    const body = lines.join('\n').trim();
    if (title && body) sections.push({ title, body });
  }
  return sections;
}

export async function fetchHealth() {
  return _getJSON('/api/health');
}

export async function fetchConfig() {
  return _getJSON('/api/config');
}

export async function fetchCities() {
  const data = await _getJSON('/api/cities');
  return { cities: (data.items || []).map((item) => item.name) };
}

export async function sendSmsCode(phone, purpose) {
  return _postJSON('/api/auth/sms/send', { phone, purpose });
}

export async function register({ phone, code, invite_code, nickname, agreed_to_terms }) {
  return _postJSON('/api/auth/register', {
    phone,
    code,
    invite_code,
    nickname,
    agreed_to_terms,
  });
}

export async function login({ phone, code }) {
  return _postJSON('/api/auth/login', { phone, code });
}

export async function guestLogin({ guestToken } = {}) {
  // 把 localStorage 里的 guest_token（如有）传给后端，让后端能找回
  // 上次的访客账号；否则后端会创建新账号并把新 token 回传给我们。
  return _postJSON('/api/auth/guest', { guest_token: guestToken || null });
}

export async function logout() {
  return _postJSON('/api/auth/logout', null);
}

export async function updateProfile({ nickname, avatar_url, mark_onboarded } = {}) {
  // 字段都是可选；undefined 不发，null/空字符串发但被后端解释成"清空"。
  const body = {};
  if (nickname !== undefined) body.nickname = nickname;
  if (avatar_url !== undefined) body.avatar_url = avatar_url;
  if (mark_onboarded) body.mark_onboarded = true;
  return _patchJSON('/api/auth/me', body);
}

export async function rerollNickname() {
  return _postJSON('/api/auth/me/reroll-nickname', null);
}

export async function uploadAvatar(file, prepareOptions) {
  // multipart/form-data — 不能用 _postJSON（那个套了 application/json）
  const preparedFile = await prepareAvatarUpload(file, prepareOptions);
  if (globalThis.location?.protocol === 'file:') {
    throw new Error('头像上传需要从 https://youshi.fun 打开，当前本地文件页面不能连接服务器');
  }
  const fd = new FormData();
  fd.append('file', preparedFile, preparedFile.name || 'avatar');
  let r;
  try {
    r = await fetch('/api/auth/avatar', {
      method: 'POST',
      credentials: 'include',
      body: fd,
    });
  } catch (err) {
    const uploadError = new Error('头像上传请求没有发出去，请检查网络后再试');
    uploadError.cause = err;
    throw uploadError;
  }
  if (!r.ok) throw await _errorFromResponse(r);
  return r.json();
}

export async function bindPhone({ phone, code }) {
  // 访客升级 — 当前 session 的 user_id 不变，只是补上 phone。
  return _postJSON('/api/auth/bind-phone', { phone, code });
}

export async function deleteAccount() {
  // 后端要求 body.confirm === 'DELETE MY ACCOUNT'，硬编码在前端
  // 是为了让"按错按钮"也无法触发；模态里第二步的输入框只是 UX 防呆，
  // 真正护栏在这里。
  const r = await fetch('/api/auth/account', {
    method: 'DELETE',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirm: 'DELETE MY ACCOUNT' }),
  });
  if (!r.ok) throw await _errorFromResponse(r);
  return r.json();
}

export async function exportMyData() {
  // 直接拿 JSON；调用方自行 Blob 化触发下载。
  return _getJSON('/api/auth/export');
}

// ============================================================================
// Billing — 订阅 + checkout（Plan 5+）
// ============================================================================

export async function fetchBilling() {
  return _getJSON('/api/billing/me');
}

export async function startCheckout({ plan, period = 'monthly', provider } = {}) {
  // body.provider 留空时后端用 settings.payment_provider — 多数前端调用不传。
  const body = { plan, period };
  if (provider) body.provider = provider;
  return _postJSON('/api/billing/checkout', body);
}

export async function cancelSubscription({ reason } = {}) {
  return _postJSON('/api/billing/cancel', { reason: reason || null });
}

export async function me() {
  const response = await fetch('/api/auth/me', { credentials: 'include' });
  if (response.status === 401) return null;
  if (!response.ok) throw await _errorFromResponse(response);
  return response.json();
}

export async function listCharts() {
  return _getJSON('/api/charts');
}

export async function getChart(chartId) {
  return _getJSON(`/api/charts/${chartId}`);
}

export async function fetchClassics(chartId) {
  return _getJSON(`/api/charts/${chartId}/classics`);
}

export async function deleteChart(chartId) {
  return _delete(`/api/charts/${chartId}`);
}

export async function restoreChart(chartId) {
  return _postJSON(`/api/charts/${chartId}/restore`, null);
}

export async function createChart({ birth_input, label }) {
  return _postJSON('/api/charts', { birth_input, label });
}

export async function fetchPaipan(payload) {
  return createChart({ birth_input: payload, label: null });
}

export async function streamSections(chartId, body, handlers = {}) {
  return streamSSE(`/api/charts/${chartId}/sections`, body, handlers);
}

export async function fetchSections(chartId) {
  const full = await streamSections(chartId, { section: 'career' });
  const sections = parseSectionsText(full);
  if (!sections.length) throw new Error('LLM returned no parseable sections');
  return { sections };
}

export async function streamVerdicts(chartId, handlers = {}) {
  return streamSSE(`/api/charts/${chartId}/verdicts`, null, handlers);
}

export async function streamDayunStep(chartId, index, handlers = {}) {
  return streamSSE(`/api/charts/${chartId}/dayun/${index}`, null, handlers);
}

export async function streamLiunian(chartId, { dayun_index, year_index }, handlers = {}) {
  return streamSSE(`/api/charts/${chartId}/liunian`, { dayun_index, year_index }, handlers);
}

// ============================================================================
// Plan 6 — conversation layer
// ============================================================================

export async function listConversations(chartId) {
  return _getJSON(`/api/charts/${chartId}/conversations`);
}

export async function createConversation(chartId, payload) {
  // payload: { label?: string, hepan_slug?: string }
  // Backwards-compat: if a string is passed, treat it as the label.
  const body = typeof payload === 'string' ? { label: payload } : (payload || {});
  return _postJSON(`/api/charts/${chartId}/conversations`, body);
}

export async function patchConversation(convId, label) {
  return _patchJSON(`/api/conversations/${convId}`, { label });
}

export async function deleteConversation(convId) {
  return _delete(`/api/conversations/${convId}`);
}

export async function restoreConversation(convId) {
  return _postJSON(`/api/conversations/${convId}/restore`, null);
}

export async function listMessages(convId, { before, limit = 50 } = {}) {
  const qs = new URLSearchParams();
  qs.set('limit', String(limit));
  if (before) qs.set('before', before);
  return _getJSON(`/api/conversations/${convId}/messages?${qs.toString()}`);
}

export async function streamMessage(convId, body, handlers = {}) {
  return streamSSE(`/api/conversations/${convId}/messages`, body, handlers);
}

export async function streamGua(convId, body, handlers = {}) {
  return streamSSE(`/api/conversations/${convId}/gua`, body, handlers);
}

export async function fetchChips(chartId, conversationId) {
  const qs = conversationId ? `?conversation_id=${conversationId}` : '';
  let final = '';
  await streamSSE(`/api/charts/${chartId}/chips${qs}`, null, {
    onDone: (full) => { final = full; },
  });
  try {
    const parsed = JSON.parse(final);
    return Array.isArray(parsed) ? parsed.filter((value) => typeof value === 'string') : [];
  } catch {
    return [];
  }
}
