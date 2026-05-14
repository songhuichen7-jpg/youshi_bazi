/** Cookie-based anonymous user id for cross-session K-factor tracking.
 *  Id format: a_ + 14 base36 chars (total 16 chars). 7-day sliding expiry.
 */
const COOKIE_NAME = 'youshi_aid';
const MAX_AGE_DAYS = 7;
const ID_RE = /^a_[a-z0-9]{14}$/;

function defaultRead() {
  return typeof document !== 'undefined' ? document.cookie : '';
}

function defaultWrite(v) {
  if (typeof document !== 'undefined') document.cookie = v;
}

function generateId() {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
  let body = '';
  for (let i = 0; i < 14; i++) body += chars[Math.floor(Math.random() * chars.length)];
  return `a_${body}`;
}

function cookieValue(id) {
  const maxAge = MAX_AGE_DAYS * 86400;
  return `${COOKIE_NAME}=${id}; Max-Age=${maxAge}; Path=/; SameSite=Lax`;
}

function parseCookie(raw, name) {
  for (const part of raw.split(';')) {
    const [k, v] = part.trim().split('=');
    if (k === name) return v;
  }
  return null;
}

export function getAnonymousId({ readCookie = defaultRead, writeCookie = defaultWrite } = {}) {
  const raw = readCookie();
  const existing = parseCookie(raw, COOKIE_NAME);
  if (existing && ID_RE.test(existing)) {
    writeCookie(cookieValue(existing));
    return existing;
  }
  const id = generateId();
  writeCookie(cookieValue(id));
  return id;
}
