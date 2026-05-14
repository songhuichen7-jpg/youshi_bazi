// frontend/src/components/hepan/HepanCard.jsx
//
// Specimen Edition pair card (v2). Replaces the previous symmetric soft-paper
// hepan card with a "dual stub" specimen plate: the front face is split down
// the middle into A-side and B-side colored fields, joined by a curator seal
// stamped across the central seam. See PM/specs/03 §三 for the data
// contract; the visual language lives in hepan.css.
//
// Front:  dual-color split panel + pair illustration + side-tinted Latin
//         binomials + central 合/和 seal · RELATION header · 文楷 pair label
//         · @nick × @nick · numbered REL tags · description · CTA · foot.
// Back:   pair index entry — role line for A and B, then the long reading
//         (description / modifier) and CTA, in the same paper chrome.
//
// saveImage.js keys off .hepan-scene, .hepan-body, .hepan-body.is-flipped,
// .hepan-front, .hepan-back-face, plus --theme / --theme-a / --theme-b
// CSS vars. Those class hooks and var names must stay.
import { forwardRef, useState } from 'react';
import { hepanPairIllustrationSrc } from '../../lib/hepanArt.js';
import { latestCardIllustrationSrc } from '../../lib/cardArt.js';
import {
  binomialFor,
  plateNumeral,
  pairSeal,
} from '../../lib/cardBinomials.js';

// Pair-edition brand mark — a sundial with TWO gnomon hands.
// One hand picks up A's accent, the other picks up B's, so the back
// reads as "two specimens kept together" without repeating any front
// information. CSS in hepan.css recolors each hand from --side-a-deep /
// --side-b-deep via attribute selectors. Hand B is mirrored through the
// center so the pair looks like two clocks sharing one face.
function PairSundial() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 100 100"
      fill="none"
      role="img"
      aria-label="有时合盘"
    >
      <circle cx="50" cy="50" r="35" fill="none" stroke="#1A1A1A" strokeWidth="2.4" />
      <path d="M50 15V85" stroke="#1A1A1A" strokeWidth="2.4" strokeLinecap="round" />
      {/* Hand A — upper right (recolored to A side accent) */}
      <path d="M50 50L73 36" stroke="#C9A96B" strokeWidth="2.8" strokeLinecap="round" data-pair="a" />
      {/* Hand B — lower left, mirrored through center (recolored to B side accent) */}
      <path d="M50 50L27 64" stroke="#C9A96B" strokeWidth="2.8" strokeLinecap="round" data-pair="b" />
      <path d="M28 73C39 80 61 81 73 69" fill="none" stroke="#1A1A1A" strokeWidth="2.4" strokeLinecap="round" />
      <circle cx="50" cy="50" r="3.2" fill="#1A1A1A" />
    </svg>
  );
}

function _displayNick(side, fallback) {
  if (!side) return fallback;
  const nick = side.nickname;
  if (nick && nick !== '游客') return nick;
  return side.cosmic_name || fallback;
}

export const HepanCard = forwardRef(function HepanCard({ hepan }, ref) {
  const [flipped, setFlipped] = useState(false);
  const a = hepan.a;
  const b = hepan.b;
  const totalTypes = '20';
  const toggleFlip = () => setFlipped(f => !f);

  const pairSrc = hepanPairIllustrationSrc(a, b);
  const altText = `${a?.cosmic_name || 'A'} × ${b?.cosmic_name || 'B'} ${hepan.category || '合盘'}插画`;

  // Roman numeral for the smaller of the two type IDs — keeps "PAIR Ⅰ" labels
  // deterministic regardless of who created the invite.
  const pairPlateId = Math.min(
    parseInt(a?.type_id || '99', 10),
    parseInt(b?.type_id || '99', 10),
  );
  const pairPlate = plateNumeral(String(pairPlateId).padStart(2, '0'));
  const sealChar = pairSeal(hepan.category);

  const nickA = _displayNick(a, '邀请人');
  const nickB = _displayNick(b, '你');

  const aBinomial = binomialFor(a?.type_id);
  const bBinomial = binomialFor(b?.type_id);

  return (
    <div
      ref={ref}
      className="hepan-scene"
      onClick={toggleFlip}
      style={{
        '--theme': hepan.pair_theme_color || '#b07a3c',
        '--theme-a': a?.theme_color || '#b07a3c',
        '--theme-b': b?.theme_color || '#b07a3c',
      }}
    >
      <div className={`hepan-body ${flipped ? 'is-flipped' : ''}`}>
        {/* ── FRONT: dual-stub specimen plate ─────────────────── */}
        <article className="hepan-face hepan-front hepan-card" data-category={hepan.category}>
          <div className="hepan-top">
            <span className="hepan-top-left">PAIR {pairPlate}</span>
            <span className="hepan-top-center">
              <span className="hepan-side-a">NO. {a?.type_id || '--'}</span>
              <span className="hepan-x">×</span>
              <span className="hepan-side-b">NO. {b?.type_id || '--'}</span>
            </span>
            <span className="hepan-top-right">有時合盤</span>
          </div>

          <div className="hepan-hero">
            <div className="hepan-anno">
              <span className="hepan-side-a">A · {a?.cosmic_name || '?'}</span>
              <span className="hepan-side-b">B · {b?.cosmic_name || '?'}</span>
            </div>

            <div className="hepan-hero-art">
              {pairSrc ? (
                <img
                  className="hepan-pair-illustration"
                  src={pairSrc}
                  alt={altText}
                  loading="eager"
                  decoding="async"
                  draggable="false"
                />
              ) : (
                <div className="hepan-pair-illustration-fallback" aria-hidden="true">
                  {a?.illustration_url ? (
                    <img src={latestCardIllustrationSrc(a.illustration_url)} alt="" draggable="false" />
                  ) : null}
                  {b?.illustration_url ? (
                    <img src={latestCardIllustrationSrc(b.illustration_url)} alt="" draggable="false" />
                  ) : null}
                </div>
              )}
            </div>

            <div className="hepan-hero-foot">
              <span className="hepan-side-a">
                <em>{aBinomial.split(' ')[0].toLowerCase()}</em>
                {a?.state ? <> · {a.state}</> : null}
              </span>
              <span className="hepan-state-pill">
                {hepan.state_pair || '⚡ × ⚡'}
              </span>
              <span className="hepan-side-b">
                <em>{bBinomial.split(' ')[0].toLowerCase()}</em>
                {b?.state ? <> · {b.state}</> : null}
              </span>
            </div>

            {sealChar ? (
              <div className="hepan-seal" aria-hidden="true">{sealChar}</div>
            ) : null}
          </div>

          <div className="hepan-label-row">
            <div className="hepan-label-stack">
              <span className="hepan-label-kicker">RELATION / 關係</span>
              <h1 className="hepan-label-name">{hepan.label || hepan.category || '搭子'}</h1>
            </div>
            <div className="hepan-nicks">
              <span className="hepan-side-a">@{nickA}</span>
              <span className="hepan-x">×</span>
              <span className="hepan-side-b">@{nickB}</span>
            </div>
          </div>

          <ul className="hepan-tags">
            {(hepan.subtags || []).slice(0, 3).map((t, i) => (
              <li key={i} className="hepan-tag">
                <span className="hepan-tag-no">REL. {String(i + 1).padStart(2, '0')}</span>
                <span className="hepan-tag-text">{t}</span>
              </li>
            ))}
          </ul>

          <div className="hepan-copy">
            {hepan.description ? (
              <p className="hepan-desc">{hepan.description}</p>
            ) : null}
            {hepan.cta ? (
              <p className="hepan-cta">「{hepan.cta}」</p>
            ) : null}
          </div>

          <div className="hepan-foot">
            <span className="hepan-foot-brand">有時合盤</span>
            <span>PAIR EDITION · youshi.app</span>
          </div>
        </article>

        {/* ── BACK: uniform pair-brand mark (dual-hand sundial) ────────
            Like the single card's brand back, but with a pair-specific
            dual-hand sundial — one hand per side, each tinted with that
            side's accent. The deck of 210 pair cards reads as one set
            because the layout is uniform; the two hand colors are the
            only thing that changes per pair. */}
        <article className="hepan-face hepan-back-face">
          <div className="hepan-top">
            <span className="hepan-top-left">REVERSE</span>
            <span className="hepan-top-center">有時合盤 / 圖鑑</span>
            <span className="hepan-top-right">PAIR {pairPlate}</span>
          </div>

          <div className="hepan-back-stage">
            <div className="hepan-back-mark"><PairSundial /></div>
            <div className="hepan-back-wordmark">
              <span className="hepan-back-wordmark-cn">有 時 合 盤</span>
              <span className="hepan-back-wordmark-en">YOUSHI · PAIR</span>
            </div>
            <div className="hepan-back-tagline">paired plates · MMXXVI</div>
            <div className="hepan-back-ref">
              <span className="hepan-back-ref-no">
                NO. <span className="hepan-side-a">{a?.type_id}</span>
                <span className="hepan-x">×</span>
                <span className="hepan-side-b">{b?.type_id}</span>
              </span>
              <span className="hepan-back-ref-name">
                <span className="hepan-side-a">{a?.cosmic_name}</span>
                <span className="hepan-x">×</span>
                <span className="hepan-side-b">{b?.cosmic_name}</span>
              </span>
            </div>
          </div>

          <div className="hepan-foot">
            <span className="hepan-foot-brand">有時合盤</span>
            <span>youshi.app · 雙人圖鑑</span>
          </div>
        </article>
      </div>
    </div>
  );
});
