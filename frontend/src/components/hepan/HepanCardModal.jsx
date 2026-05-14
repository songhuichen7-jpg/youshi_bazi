// frontend/src/components/hepan/HepanCardModal.jsx
//
// Hepan viewer as a floating overlay on top of the workspace. Replaces the
// old `/hepan/{slug}` split-page layout. The card IS the page — no side
// reading panel, no marketing CTA box, no stacked action buttons. The user
// sees the card, can flip it, and gets three actions in one compact row:
//   · 保存为图     — export the front face as PNG (saveCardAsImage)
//   · 进入解读     — ensureHepanConversation + close modal; the right-side
//                     chat panel switches to the hepan conversation, where
//                     the full reading lives as the opening AI message
//   · 关闭        — dismiss
//
// Background click + ESC also dismiss.
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppStore } from '../../store/useAppStore.js';
import { HepanCard } from './HepanCard.jsx';
import { getHepan } from '../../lib/hepanApi.js';
import { saveCardAsImage } from '../../lib/saveImage.js';
import { track } from '../../lib/analytics.js';

export function HepanCardModal({ slug, onClose }) {
  const navigate = useNavigate();
  const [hepan, setHepan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const cardRef = useRef(null);
  const closeBtnRef = useRef(null);

  // Load hepan data
  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getHepan(slug)
      .then(data => { if (!cancelled) { setHepan(data); setLoading(false); } })
      .catch(e => { if (!cancelled) { setError(e?.message || '加载失败'); setLoading(false); } });
    return () => { cancelled = true; };
  }, [slug]);

  // Dismiss on ESC
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Focus the close button after open so ESC/Tab makes sense
  useEffect(() => {
    closeBtnRef.current?.focus();
  }, []);

  // Lock body scroll while open
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, []);

  async function handleSave() {
    if (!cardRef.current || !hepan) return;
    try {
      await saveCardAsImage(cardRef.current, {
        typeId: `${hepan.a?.type_id || '00'}x${hepan.b?.type_id || '00'}`,
        cosmicName: `${hepan.a?.cosmic_name || ''}x${hepan.b?.cosmic_name || ''}`,
        onTrack: () => track('hepan_save', { slug }),
      });
    } catch (e) {
      console.error('[hepan-modal] save failed', e);
    }
  }

  async function handleEnterReading() {
    if (!hepan?.slug) return;
    const chartId = useAppStore.getState().currentId;
    if (!chartId) {
      onClose?.();
      navigate('/app');
      return;
    }
    try {
      await useAppStore.getState().ensureHepanConversation(chartId, hepan.slug);
      track('hepan_enter_reading', { slug });
    } catch (e) {
      console.error('[hepan-modal] ensureHepanConversation failed', e);
    } finally {
      // Close regardless — even on error the user will see something useful
      // in the chat panel (existing conversation or a retry path).
      onClose?.();
    }
  }

  // Backdrop click dismisses; clicks inside the dialog don't bubble out.
  function onBackdropClick(e) {
    if (e.target === e.currentTarget) onClose?.();
  }

  return (
    <div
      className="hepan-modal-backdrop"
      onClick={onBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-label="合盘卡"
    >
      <div className="hepan-modal-dialog">
        {loading ? (
          <div className="hepan-modal-loading">载入合盘…</div>
        ) : error ? (
          <div className="hepan-modal-error" role="alert">
            <p>{error}</p>
            <button type="button" className="btn-inline" onClick={onClose}>关闭</button>
          </div>
        ) : hepan ? (
          <>
            <div className="hepan-modal-stage">
              <HepanCard ref={cardRef} hepan={hepan} />
            </div>
            <div className="hepan-modal-toolbar">
              <button
                type="button"
                className="hepan-modal-action"
                onClick={handleSave}
              >
                保存为图
              </button>
              {hepan.is_creator ? (
                <button
                  type="button"
                  className="hepan-modal-action hepan-modal-action-primary"
                  onClick={handleEnterReading}
                >
                  进入解读 →
                </button>
              ) : null}
              <button
                ref={closeBtnRef}
                type="button"
                className="hepan-modal-action hepan-modal-action-ghost"
                onClick={onClose}
              >
                关闭
              </button>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
