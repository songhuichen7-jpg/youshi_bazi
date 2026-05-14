function normalizePhone(rawPhone) {
  const digits = String(rawPhone || '').replace(/\D/g, '');
  if (digits.length === 11) return digits;
  if (digits.length === 13 && digits.startsWith('86')) return digits.slice(2);
  return '';
}

export function reduceUserMenuOpen(open, action) {
  if (action?.type === 'toggle') return !open;
  if (action?.type === 'outside' || action?.type === 'logout' || action?.type === 'close') return false;
  return open;
}

const GUEST_PHONE_PREFIX = '99';   // server 给访客分配的伪手机号 99XXXXXXX

function isGuestPhone(rawPhone) {
  const digits = String(rawPhone || '').replace(/\D/g, '');
  return digits.length === 11 && digits.startsWith(GUEST_PHONE_PREFIX);
}

export function buildUserMenuProfile(user = {}) {
  const nickname = String(user?.nickname || '').trim();
  const phoneLast4 = String(user?.phone_last4 || '').trim();
  const normalizedPhone = normalizePhone(user?.phone);
  const avatarUrl = String(user?.avatar_url || '').trim() || null;
  // 访客没有真实手机号 — 后端塞的是 9912345678 这种伪号；前端不展示。
  const isGuest = isGuestPhone(user?.phone) || nickname === '游客';
  const fallbackName = isGuest ? '游客' : `尾号 ${phoneLast4 || '用户'}`;

  // 头像 fallback：有昵称用首字；游客固定 '游'；否则用尾号最后一位（保持单字符，不会撑爆 32×32 的圆头像）。
  const phoneFallbackInitial = phoneLast4 ? phoneLast4.slice(-1) : '';
  return {
    avatarUrl,
    avatarLabel: nickname
      ? Array.from(nickname)[0]
      : (isGuest ? '游' : (phoneFallbackInitial || '命')),
    displayName: nickname || fallbackName,
    isGuest,
    maskedPhone: isGuest
      ? ''   // 访客不展示伪号
      : normalizedPhone
        ? `+86 ${normalizedPhone.slice(0, 3)} *** ${normalizedPhone.slice(-4)}`
        : (phoneLast4 ? `+86 *** *** ${phoneLast4}` : ''),
    plan: ['lite', 'standard', 'pro'].includes(user?.plan) ? user.plan : 'lite',
    planExpiresAt: user?.plan_expires_at || null,
    role: user?.role === 'admin' ? 'admin' : 'user',
  };
}

// 用户中心标签 / 用量条上展示档位的中文名 — 跟后端 plan 字面值一一对应。
export function planLabel(plan) {
  if (plan === 'pro') return 'Pro';
  if (plan === 'standard') return '标准';
  return '免费体验';
}

// "Pro · 至 2026.08.31" — 用在用户中心的标签里。无到期时间则只显示档位。
export function planLabelWithExpiry(plan, expiresAt) {
  const base = planLabel(plan);
  if (!expiresAt || plan === 'lite') return base;
  const ymd = formatYearMonthDay(expiresAt);
  return ymd ? `${base} · 至 ${ymd}` : base;
}

// 7 个 daily kind + chart 共 8 类配额对应的中文短标签。
// 用户中心只展示其中 3 条最高频的（chart_message / gua / chart），
// 其余 regen / sms_send 是后台兜底用的，不进 UI。
const QUOTA_LABEL = {
  chat_message: '对话',
  gua: '起卦',
  chart: '命盘',
  section_regen: '解读重写',
  verdicts_regen: '判语重写',
  dayun_regen: '大运重写',
  liunian_regen: '流年重写',
  sms_send: '短信',
};

export function quotaKindLabel(kind) {
  return QUOTA_LABEL[kind] || kind;
}

// 把后端的 quota_snapshot 摊平成 UI 想画的三条进度条（chart_message / gua / chart）。
// kind 不在 snapshot 里就跳过 — 老版本后端可能还没填 chart 这条。
export function pickUserCenterQuotaRows(snapshot) {
  if (!snapshot || typeof snapshot !== 'object') return [];
  const usage = snapshot.usage || {};
  const rows = [];
  const chat = usage.chat_message;
  if (chat) rows.push({ kind: 'chat_message', ...chat, periodic: true });
  const gua = usage.gua;
  if (gua) rows.push({ kind: 'gua', ...gua, periodic: true });
  // 命盘是累计，不在 usage 里 — 后端单独塞在 snapshot.chart 上
  const chart = snapshot.chart;
  if (chart) rows.push({ kind: 'chart', ...chart, periodic: false });
  return rows;
}

// 生日 / 加入时间 统一格式化为「YYYY.MM」（中文环境最简洁）。
// 拿不到 / 解析失败 → 返回空字符串，让调用方决定是否兜底。
export function formatYearMonth(value) {
  if (!value) return '';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  return `${year}.${month}`;
}

// 套餐到期日要细到日 — "至 2026.05" 在五月看会让用户以为已经过期；
// "至 2026.05.31" 才足够清楚。
export function formatYearMonthDay(value) {
  if (!value) return '';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}.${month}.${day}`;
}

// 触发浏览器直接下载一个 JSON Blob — 用于"导出我的数据"。
// fallbackName 不带 .json 后缀，方法内自动加。
export function downloadJsonBlob(data, fallbackName = 'bazi-export') {
  const text = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
  const blob = new Blob([text], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '');
  const a = document.createElement('a');
  a.href = url;
  a.download = `${fallbackName}-${stamp}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // revoke 异步，立刻 revoke 在 Safari 上偶发让 download 提前中断 — 给 5s 缓冲。
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
