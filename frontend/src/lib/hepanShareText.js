// 把 hepan 邀请 URL 包装成"{邀请人} 邀请你来合个盘 — {URL}" 这样的复制文案。
// 老 HepanInviteButton 时代已经在这么做了，删该组件时把这段也丢了，这里捡回来。
//
// inviter 为空 / 'null' / '游客' 时退回到 "想跟你合个盘 — URL"，避免 "@游客 邀请..." 这种群发感。
export function composeHepanShareText(inviter, url) {
  const name = String(inviter || '').trim();
  const meaningful = name && name !== '游客';
  const prefix = meaningful ? `${name} 邀请你来合个盘` : '想跟你合个盘';
  return `${prefix} — ${url}`;
}
