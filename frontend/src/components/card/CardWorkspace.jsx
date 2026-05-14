import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAppStore } from '../../store/useAppStore';
import { useCardStore } from '../../store/useCardStore.js';
import { Card } from './Card.jsx';
import { HepanList } from '../hepan/HepanList.jsx';
import { HepanCardModal } from '../hepan/HepanCardModal.jsx';
import { PartnerBirthForm } from '../hepan/PartnerBirthForm.jsx';
import { saveCardAsImage } from '../../lib/saveImage.js';
import { copyShareLink } from '../../lib/wxShare.js';
import { composeHepanShareText } from '../../lib/hepanShareText.js';
import { invalidateHepanMine, postHepanComplete, postHepanInvite } from '../../lib/hepanApi.js';
import { bumpHepanInboxBaseline } from '../../lib/hepanInbox.js';
import { track } from '../../lib/analytics.js';

function buildShareUrl(card) {
  if (!card?.share_slug || typeof window === 'undefined') return '';
  return `${window.location.origin}/card/${card.share_slug}`;
}

function buildCurrentBirthPayload({ birthInfo, meta }) {
  const input = meta?.input || {};
  if (input.year && input.month && input.day) {
    return {
      year: input.year,
      month: input.month,
      day: input.day,
      hour: input.hour ?? -1,
      minute: input.minute ?? 0,
      city: input.city || null,
      longitude: input.longitude ?? null,
      gender: input.gender || null,
      ziConvention: input.ziConvention || 'early',
      useTrueSolarTime: input.useTrueSolarTime ?? true,
    };
  }

  if (!birthInfo?.date) return null;
  const [year, month, day] = birthInfo.date.split('-').map(s => parseInt(s, 10));
  if (!year || !month || !day) return null;
  return {
    year,
    month,
    day,
    hour: Number.isFinite(birthInfo.hour) ? birthInfo.hour : -1,
    minute: birthInfo.minute || 0,
    city: birthInfo.city || null,
    longitude: birthInfo.longitude ?? null,
    gender: birthInfo.gender || null,
    ziConvention: birthInfo.ziConvention || 'early',
    useTrueSolarTime: birthInfo.useTrueSolarTime ?? birthInfo.trueSolar ?? true,
  };
}

export function CardWorkspace() {
  const cardRef = useRef(null);
  const navigate = useNavigate();
  const currentId = useAppStore(s => s.currentId);
  const birthInfo = useAppStore(s => s.birthInfo);
  const meta = useAppStore(s => s.meta);
  const user = useAppStore(s => s.user);
  const card = useCardStore(s => s.card);
  const sourceChartId = useCardStore(s => s.sourceChartId);
  const loading = useCardStore(s => s.loading);
  const error = useCardStore(s => s.error);
  const generateFromBirthInfo = useCardStore(s => s.generateFromBirthInfo);
  const cardModeHint = useAppStore(s => s.cardModeHint);
  const setCardModeHint = useAppStore(s => s.setCardModeHint);
  const [notice, setNotice] = useState('');
  const [inviting, setInviting] = useState(false);
  const [cardMode, setCardMode] = useState(cardModeHint || 'single');
  useEffect(() => {
    if (cardModeHint) {
      setCardMode(cardModeHint);
      setCardModeHint(null);  // consume
    }
  }, [cardModeHint, setCardModeHint]);
  const [pairSubmitting, setPairSubmitting] = useState(false);
  const [pairError, setPairError] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [listReloadKey, setListReloadKey] = useState(0);
  // Slug of the hepan being viewed in the floating modal. null = no modal.
  // Clicking 「查看」 on a row in HepanList opens the modal in-place instead
  // of routing away to /hepan/{slug}.
  const [viewSlug, setViewSlug] = useState(null);
  // Bumped after every successful 生成/重生成 — passed as React key on the
  // <Card> mount so even regenerating the same cosmic_name forces a remount
  // and replays the flip-in animation. Initial value = 0 so the very first
  // render after a page reload also animates (mount === transition into view).
  const [generateTick, setGenerateTick] = useState(0);

  const activeCard = card && sourceChartId === currentId ? card : null;
  const canGenerate = !!birthInfo?.date && !!currentId;
  const shareUrl = buildShareUrl(activeCard);
  const showingSingleCard = cardMode === 'single' && !!activeCard;
  const archiveCode = cardMode === 'hepan'
    ? '我的合盘'
    : activeCard?.type_id ? `命档 ${activeCard.type_id}` : '命档待生成';
  const currentChartSummary = [
    meta?.rizhu || null,
    meta?.geju || null,
    birthInfo?.date || null,
  ].filter(Boolean).join(' · ') || '当前命盘';

  async function handleGenerate() {
    setNotice('');
    await generateFromBirthInfo({
      chartId: currentId,
      birthInfo,
      nickname: user?.nickname || null,
    });
    // Replay flip-in even when 重生成 lands on the same cosmic_name.
    setGenerateTick(t => t + 1);
  }

  async function handleSave() {
    if (!cardRef.current) return;
    if (!showingSingleCard) return;
    await saveCardAsImage(cardRef.current, {
      typeId: activeCard.type_id,
      cosmicName: activeCard.cosmic_name,
      onTrack: () => track('card_save', {
        type_id: activeCard.type_id,
        share_slug: activeCard.share_slug,
      }),
    });
  }

  async function handleShare() {
    const url = shareUrl;
    if (!url || !showingSingleCard) return;
    const copied = await copyShareLink(url, {
      clipboard: navigator.clipboard,
      notify: (message) => setNotice(message),
    });
    if (copied) {
      await track('card_share', {
        type_id: activeCard.type_id,
        channel: 'clipboard',
        share_slug: activeCard.share_slug,
      });
    }
  }

  async function createHepanInvite() {
    const birth = buildCurrentBirthPayload({ birthInfo, meta });
    if (!birth) throw new Error('当前命盘生日信息不完整，先重新排盘。');
    const nickname = user?.nickname && user.nickname !== '游客' ? user.nickname : null;
    return postHepanInvite({ birth, nickname });
  }

  async function handleCopyPairInvite() {
    if (!birthInfo?.date || inviting) return;
    setNotice('');
    setPairError('');
    setInviting(true);
    try {
      const data = await createHepanInvite();
      const inviteUrl = `${window.location.origin}/hepan/${data.slug}`;
      const inviterName = (user?.nickname && user.nickname !== '游客') ? user.nickname : null;
      const text = composeHepanShareText(inviterName, inviteUrl);
      const copied = await copyShareLink(text, {
        clipboard: navigator.clipboard,
        notify: () => {},  // 抑制默认 "链接已复制"，我们下面自己 setNotice
      });
      if (copied) {
        setNotice('已复制 — 把链接发给对方，TA 填完生日就合上了');
        invalidateHepanMine();
        setListReloadKey(k => k + 1);
        await track('hepan_invite_create', {
          slug: data.slug,
          a_type_id: data.a?.type_id,
        });
      }
    } catch (e) {
      setNotice(e.message || '邀请生成失败，再试一次。');
    } finally {
      setInviting(false);
    }
  }

  async function handlePartnerSubmit({ birth, nickname }) {
    if (pairSubmitting || !canGenerate) return;
    setPairError('');
    setNotice('');
    setPairSubmitting(true);
    try {
      const invite = await createHepanInvite();
      const completed = await postHepanComplete(invite.slug, { birth, nickname });
      // A 自己填了 B 的生日 → 这条 invite 立刻 completed_at = now。下次
      // bootstrap 的 checkHepanInbox 不应该把它误读成「B 完成了你们的合盘」
      // 弹 toast，所以这里把 inbox 基线推到这条 completed_at 之后。
      bumpHepanInboxBaseline(completed?.completed_at);
      invalidateHepanMine();
      setCreateOpen(false);
      setListReloadKey(k => k + 1);
      await track('hepan_complete_from_card', {
        slug: completed.slug,
        a_type_id: completed.a?.type_id,
        b_type_id: completed.b?.type_id,
        category: completed.category,
      });
      // 生成成功 → 直接在当前 tab 弹出合盘卡浮窗（跟「查看」按钮走同一条
      // 路径），不再开新页。保存/进入解读/关闭 都在浮窗里。
      setViewSlug(completed.slug);
    } catch (e) {
      setPairError(e?.message || '合盘生成失败，再试一次。');
    } finally {
      setPairSubmitting(false);
    }
  }

  async function handleAskFromList(item) {
    if (!item?.slug) return;
    try {
      await useAppStore.getState().ensureHepanConversation(currentId, item.slug);
      navigate('/app');
    } catch (e) {
      setNotice(e?.message || '打开对话失败，再试一次。');
    }
  }

  async function handleCopyFromList(item) {
    if (!item?.slug) return;
    const url = `${window.location.origin}/hepan/${item.slug}`;
    // 列表行复制：用本人当前的昵称包装话术。a_nickname 跟 user.nickname 通常等价，
    // 但 user.nickname 是当下值（可能后改过）；列表行的 a_nickname 是邀请那一刻的快照。
    // 两者都可，这里用当下 user.nickname 跟 handleCopyPairInvite 保持一致。
    const inviterName = (user?.nickname && user.nickname !== '游客') ? user.nickname : null;
    const text = composeHepanShareText(inviterName, url);
    const copied = await copyShareLink(text, {
      clipboard: navigator.clipboard,
      notify: () => {},
    });
    if (copied) {
      setNotice('已复制 — 把链接发给对方，TA 填完生日就合上了');
    }
  }

  return (
    <section className="card-workspace" data-mode={cardMode}>

      <div className="card-workspace-grid">
        <section className="card-controls-panel" aria-label="卡片操作">
          <div className="card-compact-bar">
            <div className="card-mode-switch" role="tablist" aria-label="卡片类型">
              <button
                type="button"
                role="tab"
                aria-selected={cardMode === 'single'}
                className={cardMode === 'single' ? 'active' : ''}
                onClick={() => {
                  setCardMode('single');
                  setNotice('');
                  setPairError('');
                }}
              >
                单人卡
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={cardMode === 'hepan'}
                className={cardMode === 'hepan' ? 'active' : ''}
                onClick={() => {
                  setCardMode('hepan');
                  setNotice('');
                  setPairError('');
                }}
              >
                合盘卡
              </button>
            </div>

            {cardMode === 'single' ? (
              <>
                <div className="card-current-summary" title={currentChartSummary}>
                  <span>{currentChartSummary}</span>
                  {activeCard ? <em>已生成</em> : null}
                </div>
                <div className="card-top-actions" aria-label="单人卡操作">
                  <button
                    type="button"
                    className="card-primary-action"
                    disabled={!canGenerate || loading}
                    onClick={handleGenerate}
                  >
                    {loading ? '生成中...' : activeCard ? '重生成' : '生成'}
                  </button>
                  <button type="button" disabled={!activeCard} onClick={handleSave}>
                    导出
                  </button>
                  <button type="button" disabled={!activeCard} onClick={handleShare}>
                    复制
                  </button>
                </div>
              </>
            ) : null}
          </div>

          {cardMode === 'hepan' ? (
            <div className="card-hepan-panel">
              <header className="card-hepan-head">
                <h2 className="card-hepan-title">我的合盘</h2>
              </header>

              {!createOpen ? (
                <div className="card-hepan-actions-row">
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => { setCreateOpen(true); setNotice(''); setPairError(''); }}
                  >+ 新建合盘</button>
                </div>
              ) : (
                <div className="card-hepan-create">
                  <PartnerBirthForm
                    submitLabel="生成合盘卡片"
                    onSubmit={handlePartnerSubmit}
                    onCancel={() => { setCreateOpen(false); setPairError(''); }}
                    busy={pairSubmitting}
                  />
                  <p className="card-hepan-fallback muted">
                    不知道对方生日？{' '}
                    <button
                      type="button"
                      className="link-button"
                      disabled={inviting}
                      onClick={async () => {
                        await handleCopyPairInvite();
                        setCreateOpen(false);
                      }}
                    >发邀请让 TA 自己填 →</button>
                  </p>
                </div>
              )}

              {notice ? <div className="card-notice">{notice}</div> : null}
              {pairError ? <div className="card-hepan-error" role="alert">{pairError}</div> : null}

              <HepanList
                onAsk={handleAskFromList}
                onCopy={handleCopyFromList}
                onView={(slug) => setViewSlug(slug)}
                reloadKey={listReloadKey}
              />
            </div>
          ) : null}

          {cardMode === 'single' && shareUrl ? (
            <div className="share-link-box">{shareUrl}</div>
          ) : null}
          {cardMode === 'single' && notice ? <div className="card-notice">{notice}</div> : null}
          {error ? <div className="form-error" role="alert">{error}</div> : null}
        </section>

        {cardMode === 'single' ? (
          <div className="card-document-stage">
            <div className="card-stage-rail" aria-hidden="true">
              <span>版式预览</span>
              <span>{archiveCode}</span>
            </div>
            <div className="card-stage-mat">
              {activeCard ? (
                <Card
                  key={`${activeCard.share_slug || activeCard.cosmic_name || 'card'}-${generateTick}`}
                  ref={cardRef}
                  card={activeCard}
                />
              ) : (
                <div
                  className="card-scene card-scene-placeholder"
                  aria-label={canGenerate ? '点击生成单人卡片' : '待生成的单人卡片'}
                  role={canGenerate ? 'button' : undefined}
                  tabIndex={canGenerate ? 0 : undefined}
                  onClick={canGenerate && !loading ? handleGenerate : undefined}
                  onKeyDown={canGenerate && !loading ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleGenerate(); } } : undefined}
                  style={{
                    '--theme': '#A0785A',
                    cursor: canGenerate && !loading ? 'pointer' : 'default',
                  }}
                >
                  <div className="card-body">
                    <div className="card-face card-front card-empty">
                      <div className="specimen-top">
                        <span className="specimen-top-left">PLATE  ?</span>
                        <span className="specimen-top-center">NO. -- / 20</span>
                        <span className="specimen-top-right">有時 / 圖鑑</span>
                      </div>
                      <div className="card-empty-body">
                        <span className="card-empty-kicker">UNCLASSIFIED · 未錄</span>
                        <span className="card-empty-prompt">{loading ? '生成中…' : '点击生成'}</span>
                      </div>
                      <div className="specimen-foot">
                        <span className="specimen-foot-brand">有時</span>
                        <span>youshi.app</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : null}
      </div>

      {viewSlug ? (
        <HepanCardModal slug={viewSlug} onClose={() => setViewSlug(null)} />
      ) : null}
    </section>
  );
}
