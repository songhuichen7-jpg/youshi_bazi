import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAppStore } from '../store/useAppStore';
import FormScreen, { LoadingScreen } from './FormScreen';
import Shell from './Shell';
import AuthScreen from './AuthScreen';
import { fetchHealth, guestLogin, me } from '../lib/api';
import { bootstrapAuthGate } from '../lib/appBootstrap';
import { scrollAndFlash } from '../lib/parseRef';
import { shouldHydrateConversation } from '../lib/chatFlow';
import ErrorState from './ErrorState';
import TooltipLayer from './TooltipLayer';
import UserMenu from './UserMenu';
import OnboardingModal from './OnboardingModal.jsx';
import FirstCardReveal, { useFirstCardReveal } from './FirstCardReveal.jsx';
import { CLASSICS_VERSION } from '../store/useAppStore';
import { devLog } from '../lib/devLog';
import { checkHepanInbox } from '../lib/hepanInbox.js';
import { invalidateHepanMine } from '../lib/hepanApi.js';

export default function AppShell() {
  const screen = useAppStore(s => s.screen);
  const user = useAppStore(s => s.user);
  const appNotice = useAppStore(s => s.appNotice);
  const clearAppNotice = useAppStore(s => s.clearAppNotice);
  const currentId = useAppStore(s => s.currentId);
  const meta = useAppStore(s => s.meta);
  const ensureConversation = useAppStore(s => s.ensureConversation);
  const loadMessages = useAppStore(s => s.loadMessages);
  const loadClassics = useAppStore(s => s.loadClassics);
  const classics = useAppStore(s => s.classics);
  const chatStreaming = useAppStore(s => s.chatStreaming);
  const guaStreaming = useAppStore(s => s.guaStreaming);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [bootstrapped, setBootstrapped] = useState(false);
  const [onboardingOpen, setOnboardingOpen] = useState(false);

  // 兜底: 'landing' state 现在归 LandingHome (访客首页) 管, AppShell 只在
  // 首次进 /app 的恢复流程里显示一个过渡态。
  // 任何路径让 store.screen 落回 'landing' (logout / session 过期 / 重置) →
  // 自动跳访客首页, 避免渲染内部旧 LandingScreen.
  useEffect(() => {
    if (!bootstrapped) return;
    if (screen === 'landing') {
      navigate('/', { replace: true });
    }
  }, [bootstrapped, screen, navigate]);

  useEffect(() => {
    if (!bootstrapped) return;
    if (!user) return;
    if (user.onboarded_at == null) {
      setOnboardingOpen(true);
    }
  }, [bootstrapped, user]);

  // 兼容老分享链接的一次性拦截 — 半年后清掉
  useEffect(() => {
    if (!bootstrapped) return;
    const hepanParam = searchParams.get('hepan');
    if (!hepanParam) return;
    const chartId = useAppStore.getState().currentId;
    if (!chartId) return;
    let cancelled = false;
    (async () => {
      try {
        await useAppStore.getState().ensureHepanConversation(chartId, hepanParam);
      } catch (e) {
        console.warn('[AppShell] hepan url intercept failed', e);
      }
      if (cancelled) return;
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.delete('hepan');
        next.delete('hepan_label');
        next.delete('hepanLabel');
        return next;
      }, { replace: true });
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bootstrapped, searchParams]);

  useEffect(() => {
    fetchHealth().then(j => {
      const llmEnabled = typeof j.llm?.hasKey === 'boolean' ? j.llm.hasKey : true;
      useAppStore.getState().setLlmStatus(llmEnabled);
      if (j.llm?.hasKey) devLog('[LLM] enabled:', j.llm.model);
    }).catch(() => {});

    ['conversations','chatHistory','gua','gua-history'].forEach(k => {
      try { localStorage.removeItem(k); } catch { /* ignore */ }
    });
    const onRefClick = (e) => scrollAndFlash(e.detail?.id);
    window.addEventListener('bazi:ref-click', onRefClick);

    let cancelled = false;
    (async () => {
      await bootstrapAuthGate({ store: useAppStore, me, guestLogin });
      if (cancelled) return;
      if (useAppStore.getState().screen === 'landing') {
        await useAppStore.getState().enterFromLanding();
      }
      if (!cancelled) setBootstrapped(true);
    })().catch(e => {
      console.error('[App] bootstrap failed', e);
      if (!cancelled) setBootstrapped(true);
    });

    return () => {
      cancelled = true;
      window.removeEventListener('bazi:ref-click', onRefClick);
    };
  }, []);

  // Real-time inbox poll — 之前只有 bootstrap 时跑一次 checkHepanInbox，导致
  // B 完成合盘后 A 必须刷新页面才能看到 toast。这里加两个轻量信号：
  //   · 标签页重新可见 / 窗口聚焦 → 立刻拉一次
  //   · 标签页可见时每 30s 轮询
  // 都不消耗配额，只是 GET /hepan/mine + 客户端 diff。
  useEffect(() => {
    if (!bootstrapped || !user?.id) return;
    const setAppNotice = useAppStore.getState().setAppNotice;
    let timer = null;
    const tick = () => {
      // 强制 bypass 30s SWR 缓存 — 我们要的是「现在的权威值」，不是缓存。
      invalidateHepanMine();
      checkHepanInbox({ setAppNotice }).catch(() => { /* 静默 */ });
    };
    const scheduleNext = () => {
      timer = setTimeout(() => {
        if (document.visibilityState === 'visible') tick();
        scheduleNext();
      }, 30_000);
    };
    const onVisible = () => {
      if (document.visibilityState === 'visible') tick();
    };
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', onVisible);
    scheduleNext();
    return () => {
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', onVisible);
      if (timer) clearTimeout(timer);
    };
  }, [bootstrapped, user]);

  useEffect(() => {
    if (!currentId || !meta) return;
    (async () => {
      // 古书定调 cache miss = idle status + 既无 persona 也无 verdict (post v2 shape)
      if ((classics?.version !== CLASSICS_VERSION) || (classics?.status === 'idle' && !classics?.persona && !classics?.verdict)) {
        void loadClassics(currentId);
      }
      const result = await ensureConversation(currentId);
      const hydration = shouldHydrateConversation({
        skipConversationHydration: useAppStore.getState().skipConversationHydration,
        conversationCreated: result?.created,
        chatStreaming: useAppStore.getState().chatStreaming,
        guaStreaming: useAppStore.getState().guaStreaming,
      });
      if (hydration.clearSkip) {
        useAppStore.setState({ skipConversationHydration: false });
        return;
      }
      if (result?.conversationId && hydration.hydrate) {
        await loadMessages(result.conversationId);
      }
    })().catch(e => console.error('[App] load conversations failed', e));
  }, [classics, currentId, meta, chatStreaming, guaStreaming, ensureConversation, loadClassics, loadMessages]);

  let content = null;
  if (screen === 'auth') content = <AuthScreen />;
  // screen === 'landing' 不再渲染内部旧 landing — bootstrap 完后由上面的
  // useEffect 兜底跳 /；bootstrap 期间显示进应用过渡态。
  else if (screen === 'landing') {
    content = !bootstrapped ? (
      <LoadingScreen title="进入中" label="正在整理你的命盘" compact />
    ) : null;
  }
  else if (screen === 'input') content = <FormScreen />;
  else if (screen === 'loading') content = <LoadingScreen />;
  else if (screen === 'shell') content = <Shell />;

  // First-card reveal — full-screen ceremony for every fresh 排盘, both
  // first-time and returning users adding a new chart. Gated by
  // localStorage per chart.id. The chartKey React key forces a remount
  // when a returning user creates another chart back-to-back, so the
  // animation replays cleanly for the new chart.
  const firstReveal = useFirstCardReveal();

  return (
    <>
      {content}
      {firstReveal.shouldShow ? (
        <FirstCardReveal key={firstReveal.chartKey} onDismiss={firstReveal.dismiss} />
      ) : null}
      <TooltipLayer />
      {user && screen !== 'auth' && screen !== 'landing' ? (
        <div className="app-header">
          <UserMenu />
        </div>
      ) : null}
      {appNotice ? (
        <div className="app-toast">
          <ErrorState
            variant="toast"
            tone={appNotice.tone || 'error'}
            title={appNotice.title}
            detail={appNotice.detail}
            retryable={false}
            cta={appNotice.cta || null}
            onDismiss={clearAppNotice}
          />
        </div>
      ) : null}
      {onboardingOpen ? (
        <OnboardingModal onClose={() => setOnboardingOpen(false)} />
      ) : null}
    </>
  );
}
