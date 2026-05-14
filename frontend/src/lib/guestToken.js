// 内测访客的稳定 token —— 存在 localStorage 里。
// 同一浏览器再次"先体验一下"时把这个 token 传给后端，后端就能找回
// 之前的访客账号 + 命盘 + 历史记录，而不是每次都创建新用户。
//
// token 不是身份凭证，只是设备记忆。后端会把它写到 users.guest_token
// 字段，并对 active 状态的用户做一对一映射。注册成功后字段会被清空。
const STORAGE_KEY = 'youshi:guest-token';

function isLocalStorageAvailable() {
  try {
    const t = '__youshi_test__';
    window.localStorage.setItem(t, t);
    window.localStorage.removeItem(t);
    return true;
  } catch {
    return false;
  }
}

function generateToken() {
  // RFC 4122 v4 hex (no dashes) — crypto.randomUUID is widely supported in
  // modern browsers; fall back to a Math.random-based variant for very old
  // environments. Either way it's only used as a stable lookup key, not a
  // cryptographic secret.
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID().replaceAll('-', '');
  }
  let s = '';
  for (let i = 0; i < 32; i += 1) {
    s += Math.floor(Math.random() * 16).toString(16);
  }
  return s;
}

export function readGuestToken() {
  if (!isLocalStorageAvailable()) return null;
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return v && v.length >= 16 ? v : null;
  } catch {
    return null;
  }
}

export function writeGuestToken(token) {
  if (!isLocalStorageAvailable()) return;
  if (!token) return;
  try {
    window.localStorage.setItem(STORAGE_KEY, token);
  } catch {
    /* swallow — private mode etc. */
  }
}

export function clearGuestToken() {
  if (!isLocalStorageAvailable()) return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* swallow */
  }
}

/** Read existing token, or generate + persist a fresh one. Returns the token. */
export function ensureGuestToken() {
  const existing = readGuestToken();
  if (existing) return existing;
  const fresh = generateToken();
  writeGuestToken(fresh);
  return fresh;
}
