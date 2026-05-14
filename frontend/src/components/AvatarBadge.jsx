import { useState } from 'react';
import { getFallbackPalette, getFallbackInitial } from '../lib/avatarFallback.js';

// 头像组件：avatarUrl 优先；否则 hash(seed) 色块 + 首字 fallback。
//
// props:
//   size       像素尺寸（24/32/40/56 等）
//   seed       hash 输入（user_id 或 hepan slug-a/-b）
//   name       昵称，用首字渲染
//   avatarUrl  可选；有就显示图片
//   className  额外类名
//
export function AvatarBadge({
  size = 32,
  seed = '',
  name = '',
  avatarUrl = null,
  className = '',
}) {
  const [imgFailed, setImgFailed] = useState(false);
  const dim = `${size}px`;
  const url = (avatarUrl || '').trim();
  // 真头像：URL 有值 + 还没失败过 → render <img>
  if (url && !imgFailed) {
    return (
      <span
        className={`avatar-badge avatar-badge-img ${className}`.trim()}
        style={{ width: dim, height: dim }}
      >
        <img
          src={url}
          alt=""
          draggable="false"
          onError={() => setImgFailed(true)}
        />
      </span>
    );
  }
  // 兜底色块
  const palette = getFallbackPalette(seed);
  const initial = getFallbackInitial(name);
  // 字号约为 size 的 0.42 — 视觉上居中、不撑边。
  const fontSize = Math.max(10, Math.round(size * 0.42));
  return (
    <span
      className={`avatar-badge avatar-badge-fallback ${className}`.trim()}
      style={{
        width: dim,
        height: dim,
        background: palette.bg,
        color: palette.ink,
        fontSize: `${fontSize}px`,
      }}
    >{initial}</span>
  );
}
