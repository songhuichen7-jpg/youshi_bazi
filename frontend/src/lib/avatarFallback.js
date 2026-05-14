// 兜底头像：在用户没传 avatar_url 时，根据稳定 seed 在 6 色调色板里选一个色块。
// seed 通常是 user_id；hepan 场景下用 `${slug}-a` / `${slug}-b` —— 同一对方在不同合盘下颜色不同，
// 这正是用户想要的（同名 cosmic 也能靠颜色区分）。
//
// 调色板：低饱和度，跟米色背景能贴。

const PALETTE = [
  { bg: '#A87E5C', ink: '#fff' },  // 暖棕
  { bg: '#6B7B8C', ink: '#fff' },  // 灰蓝
  { bg: '#8FA68E', ink: '#fff' },  // 苔绿
  { bg: '#C29B6E', ink: '#fff' },  // 蜜驼
  { bg: '#7D6B7B', ink: '#fff' },  // 暮紫
  { bg: '#B5A28A', ink: '#fff' },  // 亚麻
];

// djb2 — 极轻量字符串 hash，足够分散这 6 个桶。
function _hash(seed) {
  const str = String(seed || '');
  let h = 5381;
  for (let i = 0; i < str.length; i += 1) {
    h = ((h << 5) + h + str.charCodeAt(i)) | 0;
  }
  return h >>> 0;  // unsigned 32-bit
}

export function getFallbackPalette(seed) {
  return PALETTE[_hash(seed) % PALETTE.length];
}

// 取昵称首字（含中文一字）；空串时返回 '?'.
export function getFallbackInitial(name) {
  const trimmed = String(name || '').trim();
  if (!trimmed) return '?';
  return Array.from(trimmed)[0];
}

export const _PALETTE_FOR_TEST = PALETTE;
