import { cardIllustrationSrc } from '../../lib/cardArt.js';

export const LANDING_ILLUSTRATIONS = {
  bamboo: { alt: '春笋', filename: '01-chunsun.png' },
  samoye: { alt: '萨摩耶', filename: '03-samoye.png' },
  lamp: { alt: '小夜灯', filename: '08-xiaoyedeng.png' },
  puffer: { alt: '河豚', filename: '14-hetun.png' },
  dandelion: { alt: '蒲公英', filename: '20-pugongying.png' },
};

export function landingIllustrationSrc(kind) {
  const item = LANDING_ILLUSTRATIONS[kind] || LANDING_ILLUSTRATIONS.bamboo;
  return cardIllustrationSrc(item.filename);
}

export function landingIllustrationAlt(kind) {
  const item = LANDING_ILLUSTRATIONS[kind] || LANDING_ILLUSTRATIONS.bamboo;
  return item.alt;
}
