// frontend/src/components/landing/CosmicCardPreview.jsx
//
// 静态卡片预览组件，专给 landing 页用。复用 share-card 的视觉语言但
// 不依赖 cardStore / API — landing 上展示的是预设示例。
//
// size:
//   'hero'  — 240px 宽 (Hero 区主角)
//   'small' — 自适应 flex (Gallery 4 张并排)

import { landingIllustrationAlt, landingIllustrationSrc } from './landingIllustrations.jsx';
import { useWhiteBgRemovedImage } from '../../lib/useWhiteBgRemovedImage.js';

export function CosmicCardPreview({
  id,
  name,
  suffix,
  oneLiner,
  subtags,
  golden,
  theme,
  illustKind,
  size = 'small',
}) {
  const illustrationSrc = landingIllustrationSrc(illustKind);
  const processedIllustrationSrc = useWhiteBgRemovedImage(illustrationSrc);
  const illustrationAlt = landingIllustrationAlt(illustKind);
  return (
    <article
      className={`landing-card-preview landing-card-${size}`}
      style={{ '--theme': theme }}
    >
      <header className="landing-card-head">
        <span>有时</span>
        <span className="landing-card-typeid">
          {id} <em>/ 20</em>
        </span>
      </header>
      <div className="landing-card-illustration">
        {processedIllustrationSrc ? (
          <img
            src={processedIllustrationSrc}
            alt={illustrationAlt}
            loading="eager"
            decoding="async"
            draggable="false"
          />
        ) : null}
      </div>
      <h3 className="landing-card-name">{name}</h3>
      <p className="landing-card-suffix">· {suffix} ·</p>
      <p className="landing-card-oneliner">{oneLiner}</p>
      {subtags && subtags.length === 3 ? (
        <ul className="landing-card-subtags">
          {subtags.map((t, i) => <li key={i}>{t}</li>)}
        </ul>
      ) : null}
      {golden ? (
        <blockquote className="landing-card-golden">
          <span className="landing-card-quote">"</span>{golden}
        </blockquote>
      ) : null}
      <footer className="landing-card-foot">
        <span>有时</span>
        <span>youshi.app</span>
      </footer>
    </article>
  );
}
