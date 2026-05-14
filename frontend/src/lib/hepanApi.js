// frontend/src/lib/hepanApi.js
//
// Thin wrappers over /api/hepan/* — mirrors cardApi.js for consistency.
import { ApiError } from './cardApi.js';

const DEFAULT_BASE = '';  // same-origin

export async function postHepanInvite(payload, { fetchImpl = fetch, baseUrl = DEFAULT_BASE } = {}) {
  // credentials:'include' — 登录态时让后端把 user_id 绑到这条 invite 上。
  // 匿名调用（没 cookie）后端 optional_user 自然 fallback 到 user_id=NULL，
  // 一份代码两套用法。
  const resp = await fetchImpl(`${baseUrl}/api/hepan/invite`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new ApiError(data.detail || `request failed (${resp.status})`, resp.status);
  return data;
}

// ── /mine SWR cache ────────────────────────────────────────────────
// 这一份历史在好几个地方拉：appBootstrap 起 toast 检查、CardWorkspace 合盘
// tab、MyHepanPage 整页。单 session 内每次都走一次网络太冤 — bootstrap
// 早就拉过了，列表却还转一圈"正在拉取历史…"很慢。
//
// 模式：stale-while-revalidate。
//   · getHepanMineCached() 同步返回最近一次成功的 data（可能为 null）
//   · getHepanMine() 走 fetch；30s 内重入复用 in-flight promise，避免
//     CardWorkspace 合盘 tab 刚切过去多个 effect 同时打接口
//   · patchHepanMineCache() 给本地 mutation（新建邀请 / 删除）用，让缓
//     存跟 UI optimistic 状态一起前进，下一个消费者打开拿到的不是旧
//     列表
//
// force: true 强制 bypass — 给"我刚改完，立即拉一遍权威版"的场景留口。
let _mineCache = null;       // { ts: ms, data: {items} }
let _mineInflight = null;    // Promise<data> | null
const MINE_FRESH_MS = 30_000;

export function getHepanMineCached() {
  return _mineCache?.data || null;
}

export function patchHepanMineCache(updater) {
  if (!_mineCache?.data) return;
  const next = updater(_mineCache.data);
  if (next) _mineCache = { ts: _mineCache.ts, data: next };
}

export function invalidateHepanMine() {
  _mineCache = null;
}

// 登录用户的合盘历史。匿名 401。
// 默认 30s 内复用 cache；force:true 强制刷。in-flight dedup — 同一时间多
// 个调用方共享一个网络请求。
export async function getHepanMine({
  fetchImpl = fetch,
  baseUrl = DEFAULT_BASE,
  force = false,
} = {}) {
  if (!force) {
    const fresh = _mineCache && (Date.now() - _mineCache.ts) < MINE_FRESH_MS;
    if (fresh) return _mineCache.data;
    if (_mineInflight) return _mineInflight;
  }

  const promise = (async () => {
    const resp = await fetchImpl(`${baseUrl}/api/hepan/mine`, { credentials: 'include' });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new ApiError(data.detail || `request failed (${resp.status})`, resp.status);
    _mineCache = { ts: Date.now(), data };
    return data;
  })();
  _mineInflight = promise;
  try {
    return await promise;
  } finally {
    if (_mineInflight === promise) _mineInflight = null;
  }
}

// 软删一条邀请。后端只允许创建者本人删；其他人 / 不存在 / 已删都 404。
export async function deleteHepanInvite(slug, { fetchImpl = fetch, baseUrl = DEFAULT_BASE } = {}) {
  const resp = await fetchImpl(
    `${baseUrl}/api/hepan/${encodeURIComponent(slug)}`,
    { method: 'DELETE', credentials: 'include' },
  );
  if (resp.status === 204) {
    // 同步删 cache 里的对应行 — 下次有人 getHepanMineCached() 拿到的是新的
    patchHepanMineCache((prev) => ({
      ...prev,
      items: (prev.items || []).filter((it) => it.slug !== slug),
    }));
    return { ok: true };
  }
  const data = await resp.json().catch(() => ({}));
  throw new ApiError(data.detail || `request failed (${resp.status})`, resp.status);
}

// 合盘对话历史（仅创建者）。匿名 / 非创建者 → 401 / 404。
export async function getHepanMessages(slug, { fetchImpl = fetch, baseUrl = DEFAULT_BASE } = {}) {
  const resp = await fetchImpl(
    `${baseUrl}/api/hepan/${encodeURIComponent(slug)}/messages`,
    { credentials: 'include' },
  );
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new ApiError(data.detail || `request failed (${resp.status})`, resp.status);
  return data;
}

export async function postHepanComplete(slug, payload, { fetchImpl = fetch, baseUrl = DEFAULT_BASE } = {}) {
  const resp = await fetchImpl(
    `${baseUrl}/api/hepan/${encodeURIComponent(slug)}/complete`,
    {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  );
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new ApiError(data.detail || `request failed (${resp.status})`, resp.status);
  return data;
}

export async function getHepan(slug, { fetchImpl = fetch, baseUrl = DEFAULT_BASE } = {}) {
  const resp = await fetchImpl(`${baseUrl}/api/hepan/${encodeURIComponent(slug)}`);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new ApiError(data.detail || `request failed (${resp.status})`, resp.status);
  return data;
}
