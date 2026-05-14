// 把合盘卡片 + reading + 对话拼成 markdown 让用户下载。三段都是可选的，
// 缺哪段就跳哪段：
//   · 卡片永远有（pending / completed 都行）
//   · reading 只在 has-reading + 用户档位够时拉到（lite 拉 /reading 会 402）
//   · chat 只创建者本人能拉（其他人 401/404）
//
// 输出文件名： hepan-{slug}-{date}.md。下载完不撤 URL.revokeObjectURL，
// Safari 偶尔会因此中断 download；setTimeout 5s 再 revoke。

import { getHepan } from './hepanApi.js';
import { getHepanMessages } from './hepanApi.js';

function _fmt(date) {
  const d = date instanceof Date ? date : new Date(date);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function composeHepanMarkdown({
  hepan, readingText, messages, includeChat,
}) {
  const lines = [];
  const aName = hepan?.a?.nickname || 'A';
  const bName = hepan?.b?.nickname || 'B';
  const aCosmic = hepan?.a?.cosmic_name || '';
  const bCosmic = hepan?.b?.cosmic_name || '';
  const label = hepan?.label || '';
  const category = hepan?.category || '';
  const subtags = (hepan?.subtags || []).join(' / ');

  lines.push(`# ${label || '合盘'}`);
  if (category) lines.push(`*${category}*`);
  lines.push('');
  lines.push(`@${aName}（${aCosmic}）× @${bName}（${bCosmic}）`);
  lines.push('');

  if (subtags) {
    lines.push(`> ${subtags}`);
    lines.push('');
  }
  if (hepan?.description) {
    lines.push(hepan.description);
    lines.push('');
  }
  if (hepan?.modifier) {
    lines.push(`*${hepan.modifier}*`);
    lines.push('');
  }
  if (hepan?.cta) {
    lines.push(`> 「${hepan.cta}」`);
    lines.push('');
  }

  if (hepan?.a?.role || hepan?.b?.role) {
    lines.push('## 角色');
    lines.push('');
    if (hepan?.a?.role) lines.push(`- @${aName}（${aCosmic}）：${hepan.a.role}`);
    if (hepan?.b?.role) lines.push(`- @${bName}（${bCosmic}）：${hepan.b.role}`);
    lines.push('');
  }

  if (readingText) {
    lines.push('## 完整解读');
    lines.push('');
    lines.push(readingText.trim());
    lines.push('');
  }

  if (includeChat && messages && messages.length > 0) {
    lines.push('## 我们后续聊到的');
    lines.push('');
    for (const m of messages) {
      if (m.role === 'user') {
        lines.push(`### ${aName} 问`);
        lines.push('');
        lines.push(`> ${(m.content || '').trim().replace(/\n/g, '\n> ')}`);
      } else if (m.role === 'assistant') {
        lines.push('### AI 回应');
        lines.push('');
        lines.push((m.content || '').trim());
      }
      lines.push('');
    }
  }

  lines.push('---');
  lines.push('');
  lines.push('— 有时 · youshi.app');
  lines.push('');
  return lines.join('\n');
}

// 触发浏览器下载一段 markdown。Safari 上立刻 revoke 偶发让 download 提前
// 中断，给 5 秒缓冲再 revoke（跟 userMenu.downloadJsonBlob 同套思路）。
function _downloadMarkdown(text, filename) {
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

// 一站式：拉 hepan + reading（lite/匿名时跳过）+ messages（仅创建者）→
// 拼 markdown → 下载。调用方传 ``isCreator`` 决定要不要尝试拉对话；
// 不可访问的段落自动跳过，不抛错。
export async function downloadHepanMarkdown({ slug, isCreator }) {
  // 1. 卡片信息一定有 — 进入页面已经拉过；用 hepanApi.getHepan 重新拿确保 fresh
  const hepan = await getHepan(slug);

  // 2. reading：调 /reading 走 cache hit (instant)；402/401 时 readingText 留空
  let readingText = '';
  try {
    const r = await fetch(`/api/hepan/${encodeURIComponent(slug)}/reading`, {
      method: 'POST',
      credentials: 'include',
    });
    if (r.ok) {
      // 是 SSE 流；这里只关心最后的 done.full
      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf('\n\n')) >= 0) {
          const block = buf.slice(0, idx); buf = buf.slice(idx + 2);
          if (!block.startsWith('data:')) continue;
          try {
            const o = JSON.parse(block.slice(5).trim());
            if (o.type === 'done' && typeof o.full === 'string') {
              readingText = o.full;
            }
          } catch { /* malformed line — skip */ }
        }
      }
    }
  } catch { /* 读取失败就跳过 reading 段 */ }

  // 3. chat：只创建者可拉；非创建者直接跳过
  let messages = [];
  if (isCreator) {
    try {
      const data = await getHepanMessages(slug);
      messages = (data?.items || []).filter((m) => m.content);
    } catch { /* 401/404 — 跳过 */ }
  }

  // 4. 拼 markdown + 下载
  const md = composeHepanMarkdown({
    hepan, readingText, messages, includeChat: isCreator,
  });
  const stamp = _fmt(new Date());
  const slugSafe = String(slug).replace(/[^a-zA-Z0-9_-]/g, '');
  _downloadMarkdown(md, `hepan-${slugSafe || 'export'}-${stamp}.md`);
}
