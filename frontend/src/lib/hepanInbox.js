// Bootstrap 时拉一次 /api/hepan/mine — 找出"上次看过之后才完成"的 invite，
// 给 A 弹一条 toast: "@阿谷 完成了你们的合盘 — 看看你们的关系底色 →"
//
// 哪些算"新完成"？compared 与 localStorage.youshi.hepan_seen_completed_at
// 这个时间戳。第一次访问没有 baseline，把当下时间写进 localStorage 当
// "认为以前所有都看过了"，避免一次性把存量 invite 全弹一遍打扰用户。
//
// dedup 是 client-side 的，清 localStorage 会重弹一次 — 内测够用，付费
// 上线时再升级到 server-side seen_at 列。

import { getHepanMine } from './hepanApi.js';

const STORAGE_KEY = 'youshi.hepan_seen_completed_at';

function readSeen() {
  try { return Number(localStorage.getItem(STORAGE_KEY) || 0) || 0; }
  catch { return 0; }
}

function writeSeen(ms) {
  try { localStorage.setItem(STORAGE_KEY, String(ms)); }
  catch { /* SSR / private mode */ }
}

/**
 * Push the "seen" baseline forward — call after A self-completes a hepan
 * (filling B's birth themselves from the workspace) so the next bootstrap's
 * checkHepanInbox doesn't mistake A's own completion for B's and pop the
 * "@B 完成了你们的合盘" toast.
 *
 * Pass the completion timestamp from the API response (preferred) so the
 * baseline matches the row exactly. Falls back to Date.now() when missing.
 */
export function bumpHepanInboxBaseline(completedAt) {
  let ms = Date.parse(completedAt);
  if (!Number.isFinite(ms)) ms = Date.now();
  writeSeen(ms);
}

/**
 * @param {object} options
 * @param {(notice: object|null) => void} options.setAppNotice  Zustand 的 store action
 */
export async function checkHepanInbox({ setAppNotice }) {
  let lastSeen = readSeen();
  const isFirstRun = lastSeen === 0;
  let data;
  try {
    data = await getHepanMine();
  } catch {
    return; // 401 / 网络 — 静默
  }

  const items = data?.items || [];
  const newlyCompleted = items.filter((it) => {
    if (it.status !== 'completed' || !it.completed_at) return false;
    const t = Date.parse(it.completed_at);
    return Number.isFinite(t) && t > lastSeen;
  });

  // 第一次访问 — 把 baseline 拉到当下，存量不弹
  if (isFirstRun) {
    writeSeen(Date.now());
    return;
  }

  if (newlyCompleted.length === 0) return;

  // 一次最多弹一条 toast — 同时多人完成的话给个 N 标识就够了，spam 反伤
  // 信任。多条时挑最近的当主标题，cta 跳那一条；其余 user 进 /hepan/mine 看。
  const sorted = newlyCompleted
    .slice()
    .sort((a, b) => Date.parse(b.completed_at) - Date.parse(a.completed_at));
  const head = sorted[0];
  const more = sorted.length - 1;

  const bName = head.b_nickname || head.b_cosmic_name || '一位朋友';
  const labelHint = head.label ? `「${head.label}」` : '合盘';

  setAppNotice({
    // tone:'info' — 这是好消息（对方填了生日，能看搭子标签了），不是错误。
    // 默认 ErrorState 渲染红边 + "!" 图标会让人以为是出错；info 走中性灰
    // 边 + "✦" 图标
    tone: 'info',
    title: more > 0
      ? `@${bName} 完成了${labelHint}（还有 ${more} 段新的）`
      : `@${bName} 完成了你们的${labelHint}`,
    detail: '点开看看你们的关系底色 + 完整解读',
    retryable: false,
    cta: { label: '去看看 →', to: more > 0 ? '/hepan/mine' : `/hepan/${head.slug}` },
  });

  // 写时间戳防止下次刷新再弹同一批
  const newest = Date.parse(head.completed_at);
  if (Number.isFinite(newest)) writeSeen(newest);
}
