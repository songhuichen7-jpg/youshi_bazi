import { useEffect, useState } from 'react';
import { useAppStore } from '../store/useAppStore';
import { fetchConfig, guestLogin } from '../lib/api';
import { setAuthSessionHint } from '../lib/authSessionHint.js';
import { clearAuthPhoneHint, writeAuthPhoneHint } from '../lib/authPhoneHint.js';
import { ensureGuestToken, readGuestToken, writeGuestToken } from '../lib/guestToken.js';
import { checkHepanInbox } from '../lib/hepanInbox.js';
import SmsSendForm from './SmsSendForm';
import RegisterForm from './RegisterForm';
import LoginForm from './LoginForm';
import { friendlyError } from '../lib/errorMessages.js';

export default function AuthScreen() {
  const setUser = useAppStore(s => s.setUser);
  const enterFromLanding = useAppStore(s => s.enterFromLanding);
  const setAppNotice = useAppStore(s => s.setAppNotice);

  const [mode, setMode] = useState('register');
  const [phone, setPhone] = useState('');
  const [requireInvite, setRequireInvite] = useState(false);
  const [guestLoginEnabled, setGuestLoginEnabled] = useState(null);
  const [guestLoading, setGuestLoading] = useState(false);
  const [guestError, setGuestError] = useState('');
  // 内测模式下默认折叠"注册/登录"，露出的是单一入口"先体验一下"。
  // 已经体验过的（localStorage 有 guest_token）回访时也走同一按钮，
  // 后端会按 token 还原账号 → 命盘 + 对话 + 古籍缓存 都在。
  const hasReturningGuest = !!readGuestToken();
  const [showFullAuth, setShowFullAuth] = useState(false);

  useEffect(() => {
    fetchConfig()
      .then((config) => {
        setRequireInvite(!!config.require_invite);
        setGuestLoginEnabled(!!config.guest_login_enabled);
      })
      .catch(() => {
        setGuestLoginEnabled(false);
      });
  }, []);

  async function onAuthSuccess(user) {
    const normalizedPhone = String(phone || '').trim();
    setAuthSessionHint();
    writeAuthPhoneHint(normalizedPhone);
    setUser(normalizedPhone ? { ...user, phone: normalizedPhone } : user);
    // 跟 onGuestLogin 一致:fire-and-forget 预热 /api/hepan/mine 缓存,
    // 让用户后续点"合盘"弹层时直接走 cache,不被 chart-load 期间的
    // 连接池挤压。
    void Promise.resolve().then(() =>
      checkHepanInbox({ setAppNotice }).catch(() => { /* 静默 */ })
    );
    // 让 enterFromLanding 决定下一屏：有命盘 → shell（带数据），没有 → input。
    // 直接 setScreen('input') 会让回访用户错过自己的命盘历史。
    await enterFromLanding();
  }

  async function onGuestLogin() {
    if (guestLoading) return;
    setGuestError('');
    setGuestLoading(true);
    try {
      // 第一次进入时生成 token；再次进入时读出来传给后端，后端按 token
      // 找回上次的访客账号 → 命盘 + 对话 + 古籍缓存全部沿用。
      const token = ensureGuestToken();
      const result = await guestLogin({ guestToken: token });
      // 后端可能返回它认定的最终 token（首次进入返回的就是我们传过去的；
      // 如果客户端 token 损坏后端会创建新账号）。以后端为准写回。
      if (result.guest_token) writeGuestToken(result.guest_token);
      setAuthSessionHint();
      clearAuthPhoneHint();
      setUser(result.user || null);
      // 后台预热 /api/hepan/mine 缓存 — fire-and-forget。
      // 不挂在 await 上,因为登录跳转流不能等它;但提前打,等用户后续
      // 点开"合盘"弹层时缓存大概率已经填好,免去那个最坏 51s 的卡顿
      // (chart-load 期间 Chrome HTTP/1 连接池被挤满,/mine 拉不下来)。
      void Promise.resolve().then(() =>
        checkHepanInbox({ setAppNotice }).catch(() => { /* 静默 */ })
      );
      // 复用主入口的"决定下一屏"逻辑：回访 + 后端有命盘 → shell；
      // 全新访客或服务端没数据 → input。直接 setScreen('input')
      // 会让"继续我的命盘"按钮等于"重新填生辰"，与按钮文案矛盾。
      await enterFromLanding();
    } catch (error) {
      setGuestError(friendlyError(error, 'auth').title);
    } finally {
      setGuestLoading(false);
    }
  }

  // 内测模式：guest_login_enabled 为 true 且用户没主动展开"使用账号注册"
  // 时，渲染极简的"先体验一下"入口；其余情况渲染完整的注册/登录面板。
  const showBetaEntry = guestLoginEnabled === true && !showFullAuth;

  if (guestLoginEnabled === null) {
    return (
      <div className="screen active">
        <div className="center-wrap">
          <div className="auth-wrap auth-wrap-beta fade-in">
            <div className="section-num" style={{ marginBottom: 24 }}>有 时 · 内 测</div>
            <h1 className="serif auth-title">正在准备体验入口</h1>
          </div>
        </div>
      </div>
    );
  }

  if (showBetaEntry) {
    return (
      <div className="screen active">
        <div className="center-wrap">
          <div className="auth-wrap auth-wrap-beta fade-in">
            <div className="section-num" style={{ marginBottom: 24 }}>有 时 · 内 测</div>
            <h1 className="serif auth-title">
              {hasReturningGuest ? '欢迎回来' : '欢迎来体验'}
            </h1>
            <p className="auth-subtitle">
              {hasReturningGuest
                ? '点下方按钮直接进入。你之前的命盘、对话和古籍记录都还在。'
                : '不用注册，点下面的按钮直接进入。命盘和对话会保存在这个浏览器里，下次回来还能继续。'}
            </p>

            <button
              type="button"
              className="auth-cta-primary"
              onClick={() => void onGuestLogin()}
              disabled={guestLoading}
            >
              {guestLoading
                ? '进入体验中…'
                : hasReturningGuest
                  ? '继续我的命盘 →'
                  : '先体验一下 →'}
            </button>

            {guestError ? (
              <div className="auth-inline-error" style={{ marginTop: 16 }}>{guestError}</div>
            ) : null}

            <div className="auth-beta-foot">
              <button
                type="button"
                className="auth-link"
                onClick={() => setShowFullAuth(true)}
                disabled={guestLoading}
              >
                有手机号？用账号注册或登录
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="screen active">
      <div className="center-wrap">
        <div className="auth-wrap fade-in">
          <div className="section-num" style={{ marginBottom: 24 }}>先登录，再开始排盘</div>
          <h1 className="serif auth-title">把你的命盘存在你自己的账号里</h1>
          <p className="auth-subtitle">
            用短信验证码注册或登录。登录后，命盘、对话和起卦记录都会跟着这个账号走。
          </p>

          <div className="auth-toggle">
            <button
              className={'auth-toggle-btn' + (mode === 'register' ? ' active' : '')}
              onClick={() => setMode('register')}
              disabled={guestLoading}
            >
              注册
            </button>
            <button
              className={'auth-toggle-btn' + (mode === 'login' ? ' active' : '')}
              onClick={() => setMode('login')}
              disabled={guestLoading}
            >
              登录
            </button>
            {guestLoginEnabled ? (
              <button
                className="auth-toggle-btn"
                onClick={() => setShowFullAuth(false)}
                disabled={guestLoading}
              >
                返回体验入口
              </button>
            ) : null}
          </div>

          <div className="auth-panel">
            <SmsSendForm
              phone={phone}
              onPhoneChange={setPhone}
              purpose={mode}
            />

            <div className="divider auth-divider" />

            {mode === 'register' ? (
              <RegisterForm
                phone={phone}
                requireInvite={requireInvite}
                onSuccess={onAuthSuccess}
              />
            ) : (
              <LoginForm
                phone={phone}
                onSuccess={onAuthSuccess}
              />
            )}

            {guestError ? (
              <div className="auth-inline-error">{guestError}</div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
