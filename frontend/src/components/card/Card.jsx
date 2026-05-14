// frontend/src/components/card/Card.jsx
//
// Specimen Edition share card (v6). Front is the museum specimen plate
// (illustration + binomial + name + tags + field note). Back is a uniform
// brand-mark face — the sundial 有時 logo + wordmark + a small type
// reference at the bottom, so face-down cards stay identifiable. Same
// back per card, only the gnomon hand and bottom rule pick up the
// per-type accent, so a deck of 20 reads as one curated set.
//
// Earlier v5 had a back face that duplicated front content (name /
// binomial / suffix again). v6 swaps that out for a brand-only back so
// the front carries all the data and the back becomes a collectible mark.
//
// saveImage.js still looks for `.card-scene`, `.card-front`, `.card-back`
// and the .card-body.is-flipped class to do its flat clone for html2canvas
// export, so those outer hooks stay even though the back content changed.
import { forwardRef, useState } from 'react';
import { latestCardIllustrationSrc } from '../../lib/cardArt.js';
import { useWhiteBgRemovedImage } from '../../lib/useWhiteBgRemovedImage.js';
import {
  binomialFor,
  plateNumeral,
  gejuStem,
} from '../../lib/cardBinomials.js';

// Inline brand mark (sundial) so we don't pay a network round-trip per card
// AND can recolor the gnomon hand via CSS attribute selectors (see card.css).
function BrandSundial() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 100 100"
      fill="none"
      role="img"
      aria-label="有时"
    >
      <circle cx="50" cy="50" r="35" fill="none" stroke="#1A1A1A" strokeWidth="2.4" />
      <path d="M50 15V85" stroke="#1A1A1A" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M50 50L73 36" stroke="#C9A96B" strokeWidth="2.6" strokeLinecap="round" />
      <path d="M28 73C39 80 61 81 73 69" fill="none" stroke="#1A1A1A" strokeWidth="2.4" strokeLinecap="round" />
      <circle cx="50" cy="50" r="3.2" fill="#1A1A1A" />
    </svg>
  );
}

export const Card = forwardRef(function Card({ card, interactive = true }, ref) {
  const [flipped, setFlipped] = useState(false);
  const illustrationUrl = latestCardIllustrationSrc(card.illustration_url);
  const processedSrc = useWhiteBgRemovedImage(illustrationUrl);

  const toggleFlip = () => { if (interactive) setFlipped(f => !f); };
  const totalTypes = '20';
  const plate = plateNumeral(card.type_id);
  const binomial = binomialFor(card.type_id);
  const gejuLabel = card.personality_tag || card.ge_ju || '';
  const stampText = gejuStem(gejuLabel);

  return (
    <div
      ref={ref}
      className={`card-scene${interactive ? '' : ' card-scene-static'}`}
      onClick={toggleFlip}
      style={{
        '--card-bg': card.card_bg,
        '--glow': card.glow,
        '--theme': card.theme_color,
      }}
    >
      <div className={`card-body ${flipped ? 'is-flipped' : ''}`}>
        {/* ── FRONT: specimen plate ───────────────────────────── */}
        <div className="card-face card-front">
          {/* saveImage.js still queries .card-front-dust; keep empty so the
              selector still matches (no canvas to capture). */}
          <div className="card-front-dust" aria-hidden="true" />

          <div className="specimen-top">
            <span className="specimen-top-left">PLATE {plate}</span>
            <span className="specimen-top-center">NO. {card.type_id} / {totalTypes}</span>
            <span className="specimen-top-right">有時 / 圖鑑</span>
          </div>

          <div className="specimen-hero">
            <div className="specimen-anno">
              <span>SAMPLE COLLECTED · MMXXVI</span>
              <span>STATUS · {card.state || '—'}</span>
            </div>

            <div className="specimen-hero-art">
              {processedSrc && (
                <img
                  className="specimen-illustration"
                  src={processedSrc}
                  alt={card.cosmic_name}
                  draggable="false"
                />
              )}
            </div>

            <div className="specimen-binomial">
              <em>{binomial}</em>
              {gejuLabel ? (
                <>
                  <span className="specimen-binomial-sep"> · </span>
                  {gejuLabel}
                </>
              ) : null}
            </div>

            {stampText ? (
              <div className="specimen-stamp" aria-hidden="true">
                {[...stampText].slice(0, 2).map((ch, i) => (
                  <span key={i}>{ch}</span>
                ))}
              </div>
            ) : null}
          </div>

          <div className="specimen-type">
            <h1 className="specimen-name">{card.cosmic_name}</h1>
            {card.suffix ? (
              <div className="specimen-suffix-wrap">
                <span className="specimen-suffix-kicker">SUFFIX / 後綴</span>
                <span className="specimen-suffix">{card.suffix}</span>
              </div>
            ) : null}
          </div>

          {card.one_liner ? (
            <p className="specimen-oneliner">{card.one_liner}</p>
          ) : null}

          {(card.subtags || []).length > 0 ? (
            <ul className="specimen-tags">
              {card.subtags.slice(0, 3).map((t, i) => (
                <li key={i} className="specimen-tag">
                  <span className="specimen-tag-no">FEAT. {String(i + 1).padStart(2, '0')}</span>
                  <span className="specimen-tag-text">{t}</span>
                </li>
              ))}
            </ul>
          ) : null}

          {card.golden_line ? (
            <div className="specimen-quote">
              <span className="specimen-quote-kicker">FIELD NOTE / 金句</span>
              <p className="specimen-quote-body">「{card.golden_line}」</p>
            </div>
          ) : null}

          <div className="specimen-foot">
            <span className="specimen-foot-brand">有時</span>
            <span>youshi.fun · NO. {card.type_id}</span>
          </div>
        </div>

        {/* ── BACK: uniform brand mark (Pokémon-style card back) ── */}
        <div className="card-face card-back">
          <div className="specimen-top">
            <span className="specimen-top-left">REVERSE</span>
            <span className="specimen-top-center">有時 / 圖鑑</span>
            <span className="specimen-top-right">PLATE {plate}</span>
          </div>

          <div className="specimen-back-stage">
            <div className="specimen-back-mark"><BrandSundial /></div>
            <div className="specimen-back-wordmark">
              <span className="specimen-back-wordmark-cn">有 時</span>
              <span className="specimen-back-wordmark-en">YOUSHI</span>
            </div>
            <div className="specimen-back-tagline">human plates · MMXXVI</div>
            <div className="specimen-back-ref">
              <span className="specimen-back-ref-no">NO. {card.type_id} / {totalTypes}</span>
              <span className="specimen-back-ref-name">{card.cosmic_name}</span>
            </div>
          </div>

          <div className="specimen-foot">
            <span className="specimen-foot-brand">有時</span>
            <span>youshi.fun · 人類圖鑑</span>
          </div>
        </div>
      </div>
    </div>
  );
});
