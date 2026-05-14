import { getHepanMineCached } from './hepanApi.js';

// 给一个 conversation 算出该显示的 label。优先级：
//   1. 用户主动 PATCH 改过的 label（非 NULL 非空 trim 后非空）
//   2. hepan-bound 对话：从 hepanMine cache 派生 "合盘 · A × B"
//   3. 兜底 "合盘对话"（hepan-bound 但 cache 还没拉到）/ "新对话"（普通对话）
//
// hepanMine cache 通过 getHepanMineCached() 同步取最近一次 /api/hepan/mine
// 响应；UserMenu 改 nickname 后会 invalidateHepanMine，下次拉到的就是最新。
//
// 第二参数 { getCached } 给测试注入用 — ES module 的 namespace 是 read-only
// 的，不能像 CommonJS 那样直接换 export。生产里调用方不需要传。
export function getConversationDisplayLabel(conversation, { getCached = getHepanMineCached } = {}) {
  if (!conversation) return '新对话';

  if (conversation.label && conversation.label.trim()) {
    return conversation.label;
  }

  if (conversation.hepan_slug) {
    const cache = getCached();
    const item = cache?.items?.find(h => h.slug === conversation.hepan_slug);
    if (item) {
      const a = item.a_nickname || item.a_cosmic_name || '我';
      const b = item.b_nickname || item.b_cosmic_name || '对方';
      return `合盘 · ${a} × ${b}`;
    }
    return '合盘对话';
  }

  return '新对话';
}
