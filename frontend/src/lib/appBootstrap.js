import { clearAuthSessionHint, hasAuthSessionHint, setAuthSessionHint } from './authSessionHint.js';
import { clearAuthPhoneHint, readAuthPhoneHint } from './authPhoneHint.js';
import { readGuestToken, writeGuestToken } from './guestToken.js';
import { checkHepanInbox } from './hepanInbox.js';

// 后台异步跑一次 hepan inbox 检查 — 用户登录态恢复后立刻派发。fire-and-forget
// 不 await：bootstrap 流程不等它，toast 后到也行。错误吞掉，不影响主路径。
function _kickOffHepanInbox(store) {
  void Promise.resolve().then(() =>
    checkHepanInbox({ setAppNotice: store.getState().setAppNotice })
      .catch(() => { /* 静默 */ })
  );
}

async function tryGuestRestore({ guestLogin, store }) {
  // 内测访客 silent restore — localStorage 有 guest_token 时直接调
  // /api/auth/guest 把 session 重新发出来，避免出现"会话过期 → 落到
  // AuthScreen → 必须再点一次按钮"的两步操作。
  const token = readGuestToken();
  if (!token) return null;
  try {
    const result = await guestLogin({ guestToken: token });
    if (result?.guest_token) writeGuestToken(result.guest_token);
    if (result?.user) {
      setAuthSessionHint();
      clearAuthPhoneHint();
      store.getState().setUser(result.user);
      _kickOffHepanInbox(store);
      return result.user;
    }
  } catch {
    // 静默失败 — 用户会看到 AuthScreen 兜底，可以手动点击进入
  }
  return null;
}

export async function bootstrapAuthGate({ store, me, guestLogin }) {
  // hint 表示之前登录过 — 优先走 me() 复活会话
  if (hasAuthSessionHint()) {
    try {
      const result = await me();
      if (result?.user) {
        setAuthSessionHint();
        const phone = readAuthPhoneHint();
        store.getState().setUser({ ...result.user, ...(phone ? { phone } : {}) });
        // 顺手把配额快照也吃下来 — 省掉用户中心首次打开的那次额外往返
        if (result.quota_snapshot) {
          store.getState().setQuotaSnapshot(result.quota_snapshot);
        }
        _kickOffHepanInbox(store);
        return result.user;
      }
      // me() 拿到 null = 401，清理 hint。但不 return — 继续往下试 guest_token
      clearAuthSessionHint();
      clearAuthPhoneHint();
    } catch (error) {
      store.getState().setUser(null);
      store.getState().setAppNotice({
        title: '登录状态检查失败',
        detail: error?.message || String(error),
        retryable: true,
      });
      return null;
    }
  }

  // 无 session（首次访问或会话过期）— 看看本机有没有 guest_token，有就
  // 静默换一个新 session 出来。这样内测用户刷新/隔天打开都不需要再
  // 经过 AuthScreen 点"继续我的命盘"。
  if (guestLogin) {
    const restored = await tryGuestRestore({ guestLogin, store });
    if (restored) return restored;
  }

  store.getState().setUser(null);
  return null;
}
