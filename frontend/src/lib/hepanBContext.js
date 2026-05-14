// frontend/src/lib/hepanBContext.js
//
// 临时记 B 刚提交的生日 — 服务端只存 birth_hash + type_id（隐私设计），
// 拿不到原始日期。但接下来我们想给 B 一条引流：
//   · 用 B 的生日为 B 自己再创建一条邀请（B 也想分享出去 — 病毒环）
//   · 把 B 的生日预填进 /app 的命盘表单（B 想看自己完整命盘）
// 所以在 B 这次浏览器会话里把生日临时存 localStorage，24h TTL 后清掉。
// 单条记录只跟一个 slug 绑定，B 同时打开多个邀请时后写覆盖前写 — 这是
// "上次提交的"语义，不需要多条历史。

const KEY = 'youshi.hepan_b_recent';
const TTL_MS = 24 * 60 * 60 * 1000;

export function rememberBBirth(slug, birth) {
  if (!slug || !birth) return;
  try {
    localStorage.setItem(
      KEY,
      JSON.stringify({ slug, birth, ts: Date.now() }),
    );
  } catch { /* SSR / 私密模式 */ }
}

export function readBBirthForSlug(slug) {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed?.slug !== slug) return null;
    if (Date.now() - (parsed.ts || 0) > TTL_MS) return null;
    return parsed.birth || null;
  } catch { return null; }
}

export function clearBBirth() {
  try { localStorage.removeItem(KEY); } catch { /* ignore */ }
}
