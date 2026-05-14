// frontend/src/components/hepan/HepanScreen.jsx
//
// /hepan/:slug — opens an A-created invite. Two modes:
//   - status='pending': show A's profile + form for B to fill in
//   - status='completed': show the rendered HepanCard
import { useEffect, useRef, useState } from 'react';
import { useParams, useSearchParams, Link, useNavigate } from 'react-router-dom';
import { getHepan, postHepanComplete } from '../../lib/hepanApi.js';
import { track } from '../../lib/analytics.js';
import { saveCardAsImage } from '../../lib/saveImage.js';
import { HepanCard } from './HepanCard.jsx';
import { PartnerBirthForm } from './PartnerBirthForm.jsx';
import { downloadHepanMarkdown } from '../../lib/hepanExport.js';
import { rememberBBirth } from '../../lib/hepanBContext.js';
import { useAppStore } from '../../store/useAppStore.js';
import { Card } from '../card/Card.jsx';

export function HepanScreen() {
  const { slug } = useParams();
  const [searchParams] = useSearchParams();
  const [hepan, setHepan] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const cardRef = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    if (!slug) return;
    setLoading(true);
    getHepan(slug)
      .then(data => {
        if (cancelled) return;
        setHepan(data);
        setError(null);
        track('hepan_view', {
          slug,
          status: data.status,
          from: searchParams.get('from') || 'direct',
        });
      })
      .catch(e => {
        if (cancelled) return;
        setError(e.message || '邀请链接打不开');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [slug, searchParams]);

  async function handleCompleteFromForm({ birth, nickname }) {
    if (submitting) return;
    setSubmitting(true);
    try {
      const data = await postHepanComplete(slug, { birth, nickname });
      setHepan(data);
      // 给 HepanBFunnel 记一笔 — 服务端只存 birth_hash，本地这一份是
      // 之后 "用 B 的生日发邀请 / 跳 /app 预填表单" 的唯一来源（TTL 24h）
      rememberBBirth(slug, birth);
      track('hepan_complete', {
        slug,
        category: data.category,
        state_pair: data.state_pair,
      });
    } catch (e) {
      throw e;  // PartnerBirthForm 自己 catch + 显示 e.message
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSaveHepan() {
    if (!cardRef.current || !hepan) return;
    await saveCardAsImage(cardRef.current, {
      typeId: `${hepan.a?.type_id || ''}x${hepan.b?.type_id || ''}`,
      cosmicName: hepan.label || 'hepan',
      onTrack: () => track('hepan_card_save', {
        slug,
        category: hepan.category,
        state_pair: hepan.state_pair,
      }),
    });
  }

  function buildHepanChatLabel(data) {
    const aName = data?.a?.nickname || data?.a?.cosmic_name || '我';
    const bName = data?.b?.nickname || data?.b?.cosmic_name || '对方';
    return `${aName} × ${bName}`;
  }

  async function askInMainChat() {
    if (!hepan?.slug) return;
    const chartId = useAppStore.getState().currentId;
    if (!chartId) {
      navigate('/app');
      return;
    }
    try {
      await useAppStore.getState().ensureHepanConversation(chartId, hepan.slug);
      navigate('/app');
    } catch (e) {
      console.error('[hepan] ensureHepanConversation failed', e);
      navigate(`/app?hepan=${encodeURIComponent(hepan.slug)}&hepan_label=${encodeURIComponent(buildHepanChatLabel(hepan))}`);
    }
  }

  // 文字版导出 — markdown：卡片 + 完整解读 + 创建者的对话历史。
  // 创建者拿全套；非创建者只拿卡片 + reading（如果有）。
  const [exporting, setExporting] = useState(false);
  async function handleExportText() {
    if (!hepan || exporting) return;
    setExporting(true);
    try {
      await downloadHepanMarkdown({ slug, isCreator: !!hepan.is_creator });
      track('hepan_text_export', { slug, is_creator: !!hepan.is_creator });
    } catch (e) {
      console.error('[hepan] export failed', e);
    } finally {
      setExporting(false);
    }
  }

  if (loading) {
    return <main className="hepan-screen hepan-screen-narrow hepan-loading"><p>正在打开邀请…</p></main>;
  }

  if (error) {
    return (
      <main className="hepan-screen hepan-screen-narrow hepan-error" role="alert">
        <h1>邀请链接打不开</h1>
        <p>{error}</p>
        <Link to="/" className="primary-cta">回到首页 →</Link>
      </main>
    );
  }

  if (!hepan) return null;

  if (hepan.status === 'completed') {
    // Card-only viewer: same visual language as the in-app HepanCardModal.
    // The full reading + chat have been moved into the right-side chat panel
    // in /app (via ensureHepanConversation), so this share-link page is now
    // purely the artifact + a compact toolbar. Creators see "进入对话" which
    // jumps to /app and opens the hepan conversation; non-creator B sees
    // "看看我的" as their primary forward action.
    return (
      <main className="hepan-screen hepan-screen-focus">
        <div className="hepan-focus-stage">
          <HepanCard ref={cardRef} hepan={hepan} />
        </div>
        <div className="hepan-focus-toolbar">
          <button
            type="button"
            className="hepan-modal-action"
            onClick={handleSaveHepan}
          >
            保存为图
          </button>
          {hepan.is_creator ? (
            <button
              type="button"
              className="hepan-modal-action hepan-modal-action-primary"
              onClick={askInMainChat}
            >
              进入对话 →
            </button>
          ) : (
            <Link to="/" className="hepan-modal-action hepan-modal-action-primary">
              看看我的 →
            </Link>
          )}
          {hepan.is_creator ? (
            <button
              type="button"
              className="hepan-modal-action hepan-modal-action-ghost"
              onClick={handleExportText}
              disabled={exporting}
            >
              {exporting ? '打包中…' : '导出全文'}
            </button>
          ) : null}
        </div>
      </main>
    );
  }

  // pending: 永远渲染 B 视角 — 即使 A 自己点开了链接，看到的也是
  // "@xxx 邀请你来合盘"，相当于预览 B 看到的样子。
  // 游客账号默认 nickname 是字符串 "游客" — 直接显示成 "@游客 邀请你来合盘"
  // 又冷又像群发，导致 B 转化率掉。这里做一道 fallback：把 "游客" / 空 当
  // null 处理，优先用 cosmic_name（小夜灯 / 多肉 这类有人味的代号）。
  const _aNick = hepan.a?.nickname;
  const _meaningfulNick = _aNick && _aNick !== '游客' ? _aNick : null;
  const inviterName = _meaningfulNick || hepan.a?.cosmic_name || '一位朋友';
  const a = hepan.a;

  return (
    <main
      className="hepan-screen hepan-invite-specimen"
      style={{ '--theme': a?.theme_color || '#b07a3c' }}
    >
      <header className="hepan-invite-head">
        <p className="hepan-invite-kicker">INVITE · 邀請對照</p>
        <h1 className="hepan-invite-title">@{inviterName} 邀请你来合盘</h1>
        <p className="hepan-invite-sub">把你也刻进图鉴 — 看看你们是哪种搭子</p>
      </header>

      <div className="hepan-invite-split">
        {/* Left: A's actual specimen card (non-interactive — no flip on click).
            HepanSide carries personality_tag + one_liner now, so the binomial
            line + stamp + one-liner all render naturally. Missing fields
            (suffix/subtags/golden_line) gracefully disappear via Card's
            conditional rendering. */}
        {a ? (
          <div className="hepan-invite-card-col" aria-label="邀请方的命盘卡">
            <Card card={a} interactive={false} />
          </div>
        ) : null}

        {/* Right: B's form */}
        <section className="hepan-invite-form-col">
          <div className="hepan-invite-form-stage">
            <p className="hepan-invite-form-kicker">YOUR PLATE · 填上你的</p>
            <PartnerBirthForm
              submitLabel="提交我的生日 →"
              onSubmit={handleCompleteFromForm}
              busy={submitting}
            />
            <p className="hepan-privacy-note">
              生日用于生成这次合盘卡片，并会加密保存到邀请方的合盘记录中。
            </p>
          </div>

          <Link to="/" className="hepan-invite-self-link">看看我的 →</Link>
        </section>
      </div>
    </main>
  );
}
