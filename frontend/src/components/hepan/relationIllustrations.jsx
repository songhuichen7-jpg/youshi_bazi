// frontend/src/components/hepan/relationIllustrations.jsx
//
// Six relationship archetypes share one visual language with the personal
// cards: fine-line editorial PNGs, versioned so a new art direction arrives
// cleanly through the browser cache.
import { hepanRelationArt, relationIllustrationSrc } from '../../lib/hepanArt.js';

export function RelationIllustration({ category, className }) {
  const item = hepanRelationArt(category);
  return (
    <div className={className} aria-hidden="true">
      <img
        src={relationIllustrationSrc(category)}
        alt={item.alt}
        loading="lazy"
        decoding="async"
      />
    </div>
  );
}
