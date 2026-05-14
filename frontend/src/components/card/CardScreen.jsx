// frontend/src/components/card/CardScreen.jsx
import { useEffect, useRef } from 'react';
import { useParams, useSearchParams, Link } from 'react-router-dom';
import { useCardStore } from '../../store/useCardStore.js';
import { Card } from './Card.jsx';
import { CardActions } from './CardActions.jsx';
import { CardSkeleton } from './CardSkeleton.jsx';
import { UpgradeCTA } from './UpgradeCTA.jsx';
import { latestCardIllustrationSrc } from '../../lib/cardArt.js';
import { useWhiteBgRemovedImage } from '../../lib/useWhiteBgRemovedImage.js';
import { saveCardAsImage } from '../../lib/saveImage.js';
import { configureWxShare, copyShareLink, isWeChatBrowser } from '../../lib/wxShare.js';
import { track } from '../../lib/analytics.js';

export function CardScreen() {
  const { slug } = useParams();
  const [searchParams] = useSearchParams();
  const { card, preview, loading, error, loadPreview } = useCardStore();
  const cardRef = useRef(null);
  const previewIllustrationSrc = useWhiteBgRemovedImage(
    preview ? latestCardIllustrationSrc(preview.illustration_url) : null,
  );

  useEffect(() => {
    if (!card && slug) loadPreview(slug);
  }, [slug, card, loadPreview]);

  useEffect(() => {
    if (!card) return;
    track('card_view', {
      type_id: card.type_id,
      share_slug: card.share_slug,
      from: searchParams.get('from') || 'direct',
    });
    configureWxShare(card, {
      onShare: (channel) => track('card_share', {
        type_id: card.type_id,
        channel,
        share_slug: card.share_slug,
      }),
    }).catch(() => { /* silent */ });
  }, [card, searchParams]);

  if (loading) return <CardSkeleton />;
  if (error) {
    return (
      <main className="card-error-screen" role="alert">
        <div className="section-num">命盘摘录</div>
        <h1 className="serif">这张命盘摘录暂时看不到</h1>
        <p>它可能已经失效、被重新生成，或者链接有误。你可以回到首页，重新生成一张自己的命盘卡片。</p>
        <Link to="/" className="primary-cta">回到首页 →</Link>
      </main>
    );
  }

  if (card) {
    const handleSave = async () => {
      if (!cardRef.current) return;
      await saveCardAsImage(cardRef.current, {
        typeId: card.type_id,
        cosmicName: card.cosmic_name,
        onTrack: () => track('card_save', {
          type_id: card.type_id,
          share_slug: card.share_slug,
        }),
      });
    };

    const handleShare = async () => {
      if (isWeChatBrowser()) {
        alert('点击右上角菜单分享给好友');
      } else {
        const copied = await copyShareLink(window.location.href, {
          clipboard: navigator.clipboard,
          notify: window.alert.bind(window),
        });
        if (!copied) return;

        await track('card_share', {
          type_id: card.type_id,
          channel: 'clipboard',
          share_slug: card.share_slug,
        });
      }
    };

    return (
      <main className="card-screen">
        <Card ref={cardRef} card={card} />
        <CardActions
          onSave={handleSave}
          onShare={handleShare}
          onInvitePair={() => {
            // The standalone share-link page only knows the share slug, not
            // the original birth — invite creation needs raw birth data.
            // Redirect viewers to / to generate their own card first.
            window.location.href = '/?action=invite_pair';
          }}
        />
        <UpgradeCTA typeId={card.type_id} />
      </main>
    );
  }

  if (preview) {
    return (
      <main className="card-preview">
        <p className="preview-notice">
          这是{preview.nickname ? ` @${preview.nickname} ` : '一位朋友'}的命盘卡
        </p>
        {previewIllustrationSrc ? (
          <img src={previewIllustrationSrc} alt={preview.cosmic_name} />
        ) : null}
        <h2>{preview.cosmic_name}</h2>
        <p>· {preview.suffix} ·</p>
        <Link to="/" className="primary-cta">查看我的类型 →</Link>
      </main>
    );
  }

  return <CardSkeleton />;
}
