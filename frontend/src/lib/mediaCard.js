/** Helpers for rendering answer artifact cards.
 *
 *  - Search jump URLs (网易云 / 豆瓣)
 *  - Cover fetch via backend /api/media/cover for songs / movies.
 *  - Flower is a local semantic card; never hits external APIs.
 */

export const MEDIA_LABELS = {
  song: '歌曲',
  movie: '电影',
  flower: '花',
};

export const ATMOSPHERE_ASSETS = {
  movie: [
    {
      id: 'night-reading',
      src: '/static/card-atmospheres/book/night-reading.jpg',
      keywords: ['海上', '钢琴', '船', '夜', '孤独', '下船', '海'],
    },
    {
      id: 'sunset-glow',
      src: '/static/card-atmospheres/weather/sunset-glow.jpg',
      keywords: ['花样', '年华', '王家卫', '黄昏', '夕照', '暖色'],
    },
    {
      id: 'archive-drawer',
      src: '/static/card-atmospheres/book/archive-drawer.jpg',
      keywords: ['一一', '杨德昌', '记忆', '家庭', '岁月', '回望'],
    },
    {
      id: 'distant-thunder',
      src: '/static/card-atmospheres/weather/distant-thunder.jpg',
      keywords: ['爆裂', '鼓手', '压力', '雷', '风暴', '紧张'],
    },
    {
      id: 'plum-rain',
      src: '/static/card-atmospheres/weather/plum-rain.jpg',
      keywords: ['潮湿', '闷', '雨', '梅雨', '沉默'],
    },
    {
      id: 'paper-lamp',
      src: '/static/card-atmospheres/book/paper-lamp.jpg',
      keywords: ['温柔', '暖灯', '日常', '安静', '治愈'],
    },
    {
      id: 'clear-cold',
      src: '/static/card-atmospheres/weather/clear-cold.jpg',
      keywords: ['冷', '清冷', '雪', '冬', '克制'],
    },
    {
      id: 'library-rain',
      src: '/static/card-atmospheres/book/library-rain.jpg',
      keywords: ['书', '文艺', '雨窗', '慢', '长镜头'],
    },
  ],
  flower: [
    {
      id: 'rain-magnolia',
      src: '/static/card-atmospheres/flower/rain-magnolia.jpg',
      colors: ['#a9afbd', '#1c1411'],
      keywords: ['雨后玉兰', '玉兰', '白玉兰', '冷香', '清白'],
    },
    {
      id: 'half-peony',
      src: '/static/card-atmospheres/flower/half-peony.jpg',
      colors: ['#bbb2a9', '#908277'],
      keywords: ['半开芍药', '芍药', '半开', '聚拢', '力气', '含苞'],
    },
    {
      id: 'night-camellia',
      src: '/static/card-atmospheres/flower/night-camellia.jpg',
      colors: ['#1f150c', '#380006'],
      keywords: ['夜山茶', '山茶', '茶花', '暗红', '克制', '藏热'],
    },
    {
      id: 'iris-paper',
      src: '/static/card-atmospheres/flower/iris-paper.jpg',
      colors: ['#bdb9b0', '#f0e9df'],
      keywords: ['鸢尾', '纸影', '淡紫', '粉感', '折纸'],
    },
    {
      id: 'osmanthus-glass',
      src: '/static/card-atmospheres/flower/osmanthus-glass.jpg',
      colors: ['#c6bcb0', '#988b7a'],
      keywords: ['桂花', '木犀', '细碎', '金色', '玻璃', '暗香'],
    },
    {
      id: 'lotus-bowl',
      src: '/static/card-atmospheres/flower/lotus-bowl.jpg',
      colors: ['#b9b1a8', '#75685c'],
      keywords: ['莲花', '荷花', '莲', '荷', '净水', '清心'],
    },
    {
      id: 'hydrangea-rain',
      src: '/static/card-atmospheres/flower/hydrangea-rain.jpg',
      colors: ['#1c1d17', '#272b2e'],
      keywords: ['绣球', '紫阳花', '雨', '蓝绿', '湿润', '柔软'],
    },
    {
      id: 'plum-branch',
      src: '/static/card-atmospheres/flower/plum-branch.jpg',
      colors: ['#2b2219', '#534c46'],
      keywords: ['梅花', '梅枝', '疏影', '冬光', '清瘦', '韧性'],
    },
  ],
};

function stableIndex(input, length) {
  let hash = 0;
  const str = String(input || '');
  for (let i = 0; i < str.length; i += 1) {
    hash = ((hash << 5) - hash + str.charCodeAt(i)) | 0;
  }
  return Math.abs(hash) % length;
}

export function pickAtmosphereAsset(kind, title, subtitle) {
  const assets = ATMOSPHERE_ASSETS[kind];
  if (!assets?.length) return null;
  const haystack = `${title || ''} ${subtitle || ''}`.toLowerCase();
  const matched = assets.find((asset) => (
    asset.keywords.some((keyword) => haystack.includes(keyword.toLowerCase()))
  ));
  return matched || assets[stableIndex(haystack, assets.length)];
}

export function buildSearchUrl(kind, title, subtitle) {
  const q = (subtitle ? `${title} ${subtitle}` : title).trim();
  const enc = encodeURIComponent(q);
  if (kind === 'song') {
    return {
      url: `https://music.163.com/#/search/m/?s=${enc}&type=1`,
      label: '网易云搜索',
    };
  }
  if (kind === 'movie') {
    return {
      url: `https://search.douban.com/movie/subject_search?search_text=${enc}`,
      label: '豆瓣搜索',
    };
  }
  return { url: '', label: '' };
}

const coverCache = new Map();

/** Fetch a media cover (url + dominant colors + optional year) from the backend.
 *  Supports ``kind`` ∈ { song, movie }. Other card kinds fall back locally.
 *  Returns null on any failure so the caller can render the icon-only fallback.
 *  Memoised across the session so repeated mentions don't re-hit the backend. */
export async function fetchMediaCover(kind, title, subtitle) {
  if (kind !== 'song' && kind !== 'movie') return null;
  const q = `${kind}|${title}|${subtitle || ''}`;
  if (coverCache.has(q)) return coverCache.get(q);

  const params = new URLSearchParams({
    type: kind,
    title,
    ...(subtitle ? { artist: subtitle } : {}),
  });
  const promise = (async () => {
    try {
      const r = await fetch(`/api/media/cover?${params.toString()}`, { credentials: 'include' });
      if (!r.ok) return null;
      const data = await r.json();
      if (!data || !data.url) return null;
      return data;
    } catch {
      return null;
    }
  })();
  coverCache.set(q, promise);
  return promise;
}
