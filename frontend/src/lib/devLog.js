// frontend/src/lib/devLog.js
//
// Dev-only console logging — prod build 不走这个函数（被 vite tree-shake +
// 函数体短路双保险）。原本散在 chat / gua / dayun / liunian 各组件的 17 条
// console.log('[chat] modelUsed=...' / '[gua] retrieval=...' / etc.) 直接
// 暴露后端选了哪个模型 / 走了哪些古籍源 — 不算高敏感，但内测期不希望
// 用户随手 F12 看到我们用的是 deepseek-v4-pro 之类的实现细节。
//
// 用法：
//   import { devLog } from '../lib/devLog.js';
//   devLog('[chat] modelUsed=' + m);
//
// 控制：
//   - import.meta.env.DEV — vite 在 dev mode 是 true，prod build 是 false
//     prod 编译时整个函数体被短路，调用点本身仍存在但是 noop
//   - 强制开 / 关：localStorage.setItem('youshi.devlog', '1' | '0')
//     给生产环境调试用 — 用户报问题时让 TA 在 console 跑一句开 verbose
const _FORCE_KEY = 'youshi.devlog';

function _enabled() {
  if (import.meta?.env?.DEV) return true;
  try {
    const v = window?.localStorage?.getItem(_FORCE_KEY);
    return v === '1';
  } catch {
    return false;
  }
}

export function devLog(...args) {
  if (!_enabled()) return;
  console.log(...args);
}

export function devWarn(...args) {
  if (!_enabled()) return;
  console.warn(...args);
}
