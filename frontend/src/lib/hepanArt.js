export const HEPAN_ART_VERSION = 'v1.1-2026-05-relation-illustrations';
export const HEPAN_PAIR_ART_VERSION = 'v2.1-2026-05-pair-alpha';

const TYPE_SLUGS = {
  '01': '01-chunsun',
  '02': '02-xiangzi',
  '03': '03-samoye',
  '04': '04-hanxiucao',
  '05': '05-huolieniao',
  '06': '06-rekeke',
  '07': '07-yinghuochong',
  '08': '08-xiaoyedeng',
  '09': '09-daxiang',
  '10': '10-songshu',
  '11': '11-duorou',
  '12': '12-shulan',
  '13': '13-ciwei',
  '14': '14-hetun',
  '15': '15-liuli',
  '16': '16-mao',
  '17': '17-shuita',
  '18': '18-zhangyu',
  '19': '19-shuimu',
  '20': '20-pugongying',
};

const RELATION_ART = {
  '天作搭子': {
    filename: 'tianzuo.png',
    alt: '天作搭子关系插画',
  },
  '镜像搭子': {
    filename: 'mirror.png',
    alt: '镜像搭子关系插画',
  },
  '同频搭子': {
    filename: 'tongpin.png',
    alt: '同频搭子关系插画',
  },
  '滋养搭子': {
    filename: 'ziyang.png',
    alt: '滋养搭子关系插画',
  },
  '火花搭子': {
    filename: 'huohua.png',
    alt: '火花搭子关系插画',
  },
  '互补搭子': {
    filename: 'hubu.png',
    alt: '互补搭子关系插画',
  },
};

export function hepanRelationArt(category) {
  return RELATION_ART[category] || RELATION_ART['互补搭子'];
}

export function relationIllustrationSrc(category) {
  const item = hepanRelationArt(category);
  return `/static/hepan/illustrations/${item.filename}?v=${HEPAN_ART_VERSION}`;
}

function sideTypeSlug(side) {
  const normalizedId = String(side?.type_id || '').padStart(2, '0');
  if (TYPE_SLUGS[normalizedId]) return TYPE_SLUGS[normalizedId];

  const file = String(side?.illustration_url || '')
    .split('?')[0]
    .split('/')
    .pop();
  return file ? file.replace(/\.png$/i, '') : null;
}

export function hepanPairIllustrationFilename(a, b) {
  const pair = [sideTypeSlug(a), sideTypeSlug(b)].filter(Boolean);
  if (pair.length !== 2) return null;
  pair.sort((left, right) => Number(left.slice(0, 2)) - Number(right.slice(0, 2)));
  return `${pair[0]}__${pair[1]}.png`;
}

export function hepanPairIllustrationSrc(a, b) {
  const filename = hepanPairIllustrationFilename(a, b);
  if (!filename) return null;
  return `/static/hepan/illustrations/pairs-v1-alpha/${filename}?v=${HEPAN_PAIR_ART_VERSION}`;
}
