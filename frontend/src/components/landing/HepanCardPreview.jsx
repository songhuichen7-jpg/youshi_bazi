// frontend/src/components/landing/HepanCardPreview.jsx
//
// Static specimen-pair preview for the landing page (section 03 — 关系).
// Mirrors the live HepanCard visual language but at landing scale (3:4 in a
// ~340px-wide column) and with hand-picked sample data, so it never depends
// on API or auth state.
import { hepanPairIllustrationSrc } from '../../lib/hepanArt.js';

const A = { type_id: '01', cosmic_name: '春笋',   theme: '#2D6A4F' };
const B = { type_id: '08', cosmic_name: '小夜灯', theme: '#9B7AC4' };

export function HepanCardPreview() {
  const pairSrc = hepanPairIllustrationSrc(A, B);

  return (
    <article
      className="landing-hepan-preview"
      style={{
        '--side-a': A.theme,
        '--side-b': B.theme,
        '--theme-a': A.theme,
        '--theme-b': B.theme,
      }}
    >
      <header className="landing-hepan-top">
        <span className="landing-hepan-top-left">PAIR Ⅰ</span>
        <span className="landing-hepan-top-center">
          <span className="landing-hepan-side-a">NO. {A.type_id}</span>
          <span className="landing-hepan-x">×</span>
          <span className="landing-hepan-side-b">NO. {B.type_id}</span>
        </span>
        <span className="landing-hepan-top-right">有時合盤</span>
      </header>

      <div className="landing-hepan-hero">
        <div className="landing-hepan-anno">
          <span className="landing-hepan-side-a">A · {A.cosmic_name}</span>
          <span className="landing-hepan-side-b">B · {B.cosmic_name}</span>
        </div>

        <div className="landing-hepan-art">
          {pairSrc ? (
            <img
              className="landing-hepan-pair-illustration"
              src={pairSrc}
              alt="春笋 × 小夜灯 撑腰搭子插画"
              loading="eager"
              decoding="async"
              draggable="false"
            />
          ) : null}
        </div>

        <div className="landing-hepan-hero-foot">
          <span className="landing-hepan-side-a"><em>phyllostachys</em> · 綻放</span>
          <span className="landing-hepan-state-pill">⚡ × 🔋</span>
          <span className="landing-hepan-side-b"><em>lampas</em> · 蓄力</span>
        </div>

        <div className="landing-hepan-seal" aria-hidden="true">合</div>
      </div>

      <div className="landing-hepan-label-row">
        <div className="landing-hepan-label-stack">
          <span className="landing-hepan-label-kicker">RELATION / 關係</span>
          <h3 className="landing-hepan-label-name">撐腰搭子</h3>
        </div>
        <div className="landing-hepan-nicks">
          <span className="landing-hepan-side-a">@小滿</span>
          <span className="landing-hepan-x">×</span>
          <span className="landing-hepan-side-b">@阿青</span>
        </div>
      </div>

      <ul className="landing-hepan-tags">
        <li><span className="landing-hepan-tag-no">REL. 01</span><span>一個往前長</span></li>
        <li><span className="landing-hepan-tag-no">REL. 02</span><span>一個替你亮</span></li>
        <li><span className="landing-hepan-tag-no">REL. 03</span><span>靠近後更穩</span></li>
      </ul>

      <p className="landing-hepan-cta">「你衝，我在後面把燈留著。」</p>

      <footer className="landing-hepan-foot">
        <span className="landing-hepan-foot-brand">有時合盤</span>
        <span>PAIR EDITION · youshi.fun</span>
      </footer>
    </article>
  );
}
