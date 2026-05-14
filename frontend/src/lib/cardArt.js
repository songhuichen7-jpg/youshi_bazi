export const CARD_ART_VERSION = 'v4.3-2026-05-handdrawn';

export function cardIllustrationSrc(filename) {
  return `/static/cards/illustrations/${filename}?v=${CARD_ART_VERSION}`;
}

export function latestCardIllustrationSrc(src) {
  if (!src || typeof src !== 'string') return src;
  const [path] = src.split('?');
  if (!path.includes('/static/cards/illustrations/')) return src;
  return `${path}?v=${CARD_ART_VERSION}`;
}
