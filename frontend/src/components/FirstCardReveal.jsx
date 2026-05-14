// frontend/src/components/FirstCardReveal.jsx
//
// First-time card reveal — every time a user finishes a 排盘 (whether
// it's their first chart ever OR a returning user adding a new chart),
// surface their specimen card in a floating modal as a ceremonial
// "here's your specimen" moment. After dismiss the workspace continues
// normally; the per-chart localStorage flag prevents replays.
//
// Visual pattern intentionally mirrors HepanCardModal: same backdrop,
// same toolbar shape (保存为图 / 进入命盘 / 关闭), same dialog entry
// motion. Two specimen-reveal moments share one design language.
//
// Animation: subtle scale + lift + opacity, cubic-bezier(.16, 1, .3, 1)
// — what Apple/Linear use for "comes to rest" feel. Avoids the swing/
// rotateY look that's too theatrical for a quiet curator moment.
//
// Gate: localStorage flag `firstCardRevealed:{chart_id}`. Keyed by
// chart, not user — returning users adding new charts get the moment
// fresh per chart.
/* eslint-disable react-hooks/exhaustive-deps */
import { useEffect, useRef, useState } from 'react';
import { useAppStore } from '../store/useAppStore.js';
import { useCardStore } from '../store/useCardStore.js';
import { Card } from './card/Card.jsx';
import { saveCardAsImage } from '../lib/saveImage.js';
import { track } from '../lib/analytics.js';

const FLAG_PREFIX = 'firstCardRevealed:';

function hasSeenReveal(chartId) {
  if (!chartId || typeof window === 'undefined') return false;
  try {
    return !!localStorage.getItem(FLAG_PREFIX + chartId);
  } catch {
    return true;
  }
}

function markRevealSeen(chartId) {
  if (!chartId || typeof window === 'undefined') return;
  try { localStorage.setItem(FLAG_PREFIX + chartId, '1'); } catch { /* ignore */ }
}

export default function FirstCardReveal({ onDismiss }) {
  const user = useAppStore(s => s.user);
  const currentId = useAppStore(s => s.currentId);
  const birthInfo = useAppStore(s => s.birthInfo);
  const card = useCardStore(s => s.card);
  const sourceChartId = useCardStore(s => s.sourceChartId);
  const cardLoading = useCardStore(s => s.loading);
  const generateFromBirthInfo = useCardStore(s => s.generateFromBirthInfo);

  const [phase, setPhase] = useState('preparing'); // preparing | revealing | dismissing
  const generatedOnce = useRef(false);
  const cardRef = useRef(null);

  const activeCard = card && sourceChartId === currentId ? card : null;
  const ready = !!activeCard && phase !== 'dismissing';

  // Kick off generation if no fresh card yet for this chart.
  useEffect(() => {
    if (activeCard || generatedOnce.current || !currentId || !birthInfo) return;
    generatedOnce.current = true;
    generateFromBirthInfo({
      chartId: currentId,
      birthInfo,
      nickname: user?.nickname || null,
    }).catch(e => console.error('[first-reveal] card generation failed', e));
  }, [activeCard, currentId, birthInfo, user, generateFromBirthInfo]);

  // Once the card is in, swap to 'revealing' (CSS transitions kick in).
  useEffect(() => {
    if (activeCard && phase === 'preparing') {
      const id1 = requestAnimationFrame(() => {
        const id2 = requestAnimationFrame(() => setPhase('revealing'));
        return () => cancelAnimationFrame(id2);
      });
      return () => cancelAnimationFrame(id1);
    }
  }, [activeCard, phase]);

  // ESC dismisses.
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') handleDismiss(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Lock body scroll.
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, []);

  // 8s safety: if generation hangs we give up gracefully.
  useEffect(() => {
    if (phase !== 'preparing') return;
    const t = setTimeout(() => {
      console.warn('[first-reveal] timeout waiting for card; dismissing');
      handleDismiss();
    }, 8000);
    return () => clearTimeout(t);
  }, [phase]);

  function handleDismiss() {
    if (phase === 'dismissing') return;
    setPhase('dismissing');
    markRevealSeen(currentId);
    setTimeout(() => onDismiss?.(), 320);
  }

  async function handleSave() {
    if (!cardRef.current || !activeCard) return;
    try {
      await saveCardAsImage(cardRef.current, {
        typeId: activeCard.type_id,
        cosmicName: activeCard.cosmic_name,
        onTrack: () => track('card_save', {
          type_id: activeCard.type_id,
          share_slug: activeCard.share_slug,
          source: 'first_reveal',
        }),
      });
    } catch (e) {
      console.error('[first-reveal] save failed', e);
    }
  }

  function onBackdropClick(e) {
    if (e.target === e.currentTarget && ready) handleDismiss();
  }

  return (
    <div
      className={`first-reveal-modal first-reveal-${phase}`}
      onClick={onBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-label="你的命盘卡"
    >
      <div className="first-reveal-dialog">
        {activeCard ? (
          <>
            <header className="first-reveal-head">
              <span className="first-reveal-kicker">NEW PLATE · 新入册</span>
              <h2 className="first-reveal-title">你的专属命盘卡</h2>
            </header>
            <div className="first-reveal-stage">
              <Card ref={cardRef} card={activeCard} />
            </div>
            <div className="first-reveal-toolbar">
              <button
                type="button"
                className="hepan-modal-action hepan-modal-action-primary"
                onClick={handleSave}
              >
                保存为图
              </button>
              <button
                type="button"
                className="hepan-modal-action hepan-modal-action-ghost"
                onClick={handleDismiss}
              >
                关闭
              </button>
            </div>
          </>
        ) : (
          <div className="first-reveal-preparing">
            <span className="first-reveal-dots"><em /><em /><em /></span>
            <p className="first-reveal-loading-label">
              {cardLoading ? '正在为你刻一张图鉴…' : '准备中…'}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Orchestrator hook: AppShell uses this to decide if/when to mount
// the overlay. Re-checks every time the active chart changes, so a
// returning user creating their 2nd / 3rd chart still gets the moment.
export function useFirstCardReveal() {
  const user = useAppStore(s => s.user);
  const screen = useAppStore(s => s.screen);
  const currentId = useAppStore(s => s.currentId);
  const [activeForChart, setActiveForChart] = useState(null);
  const lastCheckedChartId = useRef(null);

  useEffect(() => {
    if (screen !== 'shell') return;
    if (!user?.id || !currentId) return;
    if (lastCheckedChartId.current === currentId) return;
    lastCheckedChartId.current = currentId;
    if (!hasSeenReveal(currentId)) setActiveForChart(currentId);
  }, [screen, user, currentId]);

  return {
    shouldShow: activeForChart === currentId && !!activeForChart,
    chartKey: activeForChart,
    dismiss: () => setActiveForChart(null),
  };
}
