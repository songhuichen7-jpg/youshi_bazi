import { useAppStore } from '../store/useAppStore.js';

// Two token shapes share the [[…]] syntax:
//   [[ref.id|label]]                 — chart-internal cross-references
//   [[song:title|subtitle?]]         — answer artifact cards
//   [[movie:title|director?]]
//   [[flower:name|state?]]
// Subtitle is optional for artifact tokens (artist/director/notes can be
// absent when the LLM isn't sure).
const ARTIFACT_KINDS = 'song|movie|flower';
const TOKEN_RE = new RegExp(String.raw`\[\[(?:(${ARTIFACT_KINDS}):([^|\]]+)(?:\|([^\]]+))?|([\w.一-鿿]+)\|([^\]]+))\]\]`, 'g');
// Media cards render as their own paragraph; the LLM almost always wraps
// them in \n\n which our pre-wrap parent renders as visible blank lines,
// stacking on top of the card's own margin. Strip the surrounding
// whitespace + an optional sentence-ending 。/！/？ at the parser level
// so the card sits flush against the adjacent text. Chart refs (inline
// labels) keep their punctuation/whitespace untouched.
const NBSP = '\u00a0';
const MEDIA_TRAILING_RE = new RegExp(`^[。！？.!?]?[\\s${NBSP}]*`);
const GAN = '甲乙丙丁戊己庚辛壬癸';
const ZHI = '子丑寅卯辰巳午未申酉戌亥';
const BARE_CHART_REF_RE = new RegExp(
  String.raw`(^|[^\[\w.])(?:(liunian\.\d{4})\|((?:\d{4})?[${GAN}][${ZHI}])|(dayun\.\d+)\|((?:\d{1,2}(?:-\d{1,2})?岁)?[${GAN}][${ZHI}](?:大?运)?))`,
  'g',
);

// LLMs occasionally serialise our token in malformed shapes — single brackets,
// markdown-link syntax, etc. Repair the common ones BEFORE the strict parser
// runs so users don't see "[label](url)" leak into the reply.
const FIXUP_PATTERNS = [
  // [label](url) where url looks like a chart-ref id (pillar./shishen./dayun./liunian.)
  // → [[id|label]]. Caught even when the LLM stuffed extra text into the URL.
  {
    re: /\[([^\]]+)\]\(([^)]*?(?:pillar|shishen|dayun|liunian)\.[\w.一-鿿]*)\)/g,
    repl: (_m, label, urlish) => {
      const id = String(urlish).match(/(?:pillar|shishen|dayun|liunian)\.[\w.一-鿿]+/)?.[0];
      return id ? `[[${id}|${label}]]` : _m;
    },
  },
  // Single-bracket artifact token: [song:歌|艺] → [[song:歌|艺]]
  {
    re: /(^|[^[])\[(song|movie|flower):([^|\]]+)(?:\|([^\]]+))?](?!])/g,
    repl: (_m, head, kind, title, sub) =>
      `${head}[[${kind}:${title}${sub ? '|' + sub : ''}]]`,
  },
];

function repairTokens(text) {
  let out = String(text);
  out = out.replace(BARE_CHART_REF_RE, (_m, prefix, liunianId, liunianLabel, dayunId, dayunLabel) => {
    if (liunianId) return `${prefix}[[${liunianId}|${liunianLabel}]]`;
    return `${prefix}[[${dayunId}|${dayunLabel}]]`;
  });
  for (const { re, repl } of FIXUP_PATTERNS) {
    out = out.replace(re, repl);
  }
  return out;
}

function requestedMediaKinds(context) {
  const c = String(context || '').toLowerCase();
  const kinds = new Set();
  if (/(用一首歌|用一支歌|用一首曲|哪首歌|哪一首歌|哪个歌|什么歌|哪种歌|像哪首歌|像哪一首歌|像哪个歌|像什么歌|像哪种歌|歌形容|曲形容|换一首|换首|再来一首|再来首)/.test(c)) {
    kinds.add('song');
  }
  if (/(用一部电影|用一部影片|用一部剧|用一部纪录片|哪部电影|哪一部电影|哪个电影|什么电影|哪部影片|哪一部影片|哪个影片|什么影片|像哪部电影|像哪一部电影|像哪个电影|像什么电影|像哪部影片|像哪个影片|像什么影片|电影形容|影片形容|换一部|换部|再来一部)/.test(c)) {
    kinds.add('movie');
  }
  if (!/(桃花运|烂桃花)/.test(c) && /(用一种花|用花形容|用花来形容|像什么花|像哪种花|像哪朵花|像哪一朵花|像哪一类花|像哪类花|换一种花|换朵花|换个花|再来.*花)/.test(c)) {
    kinds.add('flower');
  }
  return kinds;
}

function shouldRenderMediaToken(kind, context) {
  return requestedMediaKinds(context).has(kind);
}

// When the user explicitly asked "用一首歌/一部电影 形容…" but the LLM
// fell back to 《XX》 instead of our token format, infer the media kind from
// the question and rewrite. Only fires when the question STRONGLY signals a
// kind, so we don't accidentally turn 古籍《滴天髓》into a movie card.
function inferMediaKind(context) {
  const requested = requestedMediaKinds(context);
  if (requested.has('song')) return 'song';
  if (requested.has('movie')) return 'movie';
  // 花不做 《XX》 rescue：日常回答里"花"太常见，必须由 LLM
  // 明确输出 [[flower:...]] 才渲染，避免误触发。
  return null;
}

// Match 《X》 plus optional "—— 艺人/导演" subtitle, plus optionally an
// orphan sentence-ending punct ([。！？.!?]) ONLY when followed by newline
// or end-of-string. This eats the dangling 。 next to a card-as-sentence
// (e.g. "《肖申克的救赎》。\n\n…") without disturbing 《X》 mid-sentence
// (e.g. "我喜欢《肖申克》。它讲的是…" keeps its sentence break intact).
const TITLE_QUOTE_RE = /《([^《》]{1,40})》(?:\s*[—-]+\s*([^，。；,;.!\n\s]{1,20}))?(?:[。！？.!?](?=\s*$|\s*\n))?/g;

// 命理古籍标题黑名单 — 这些是 AI 回答里高频被引用的源文献，rescue 时必须跳过，
// 否则像"《穷通宝鉴》——1985 论三秋甲木" 这种引文会被当成第一个《X》拽进
// song / movie 卡。仓库里 5 本 + 几本常被 LLM 提到的扩展命理书。
const CLASSICS_TITLES = new Set([
  '穷通宝鉴',
  '三命通会',
  '滴天髓',
  '渊海子平',
  '子平真诠',
  '神峰通考',
  '命理探源',
  '子平粹言',
  '兰台妙选',
  '星平会海',
]);

function rescueQuotedTitles(text, kind) {
  if (!kind) return text;
  TOKEN_RE.lastIndex = 0;
  if (TOKEN_RE.test(text)) {
    TOKEN_RE.lastIndex = 0;
    return text;
  }
  TOKEN_RE.lastIndex = 0;
  // 只 rescue **第一个非古籍** 《XX》。"用一首歌 / 一部电影" 类问题答案
  // 通常就一个主题标题；后面再出现的多半是引文 / 例子，rescue 了反伤。
  // 古籍标题（穷通宝鉴 / 子平真诠 等）即便排在最前面也要跳过 — 它们是
  // AI 在引经据典，不是它要给你的"歌 / 电影"答案。
  let rescued = false;
  return text.replace(TITLE_QUOTE_RE, (match, title, sub) => {
    if (rescued) return match;
    if (CLASSICS_TITLES.has(title.trim())) return match;
    rescued = true;
    return `[[${kind}:${title.trim()}${sub ? '|' + sub.trim() : ''}]]`;
  });
}

export function parseRef(text, options = {}) {
  if (!text) return [];
  text = repairTokens(text);
  const mediaState = options.mediaState instanceof Set ? options.mediaState : null;
  const alreadyRenderedMedia = mediaState?.has('rendered') === true;
  const inferredKind = inferMediaKind(options.context);
  if (inferredKind && !alreadyRenderedMedia) text = rescueQuotedTitles(text, inferredKind);
  const out = [];
  let last = 0;
  let renderedMedia = alreadyRenderedMedia;
  TOKEN_RE.lastIndex = 0;
  let m;
  while ((m = TOKEN_RE.exec(text)) !== null) {
    const isMediaToken = !!m[1];
    const renderMediaToken = isMediaToken && shouldRenderMediaToken(m[1], options.context);
    if (m.index > last) {
      let preceding = text.slice(last, m.index);
      // Trim trailing newlines/spaces from the segment before a media card —
      // the card has its own margin and doesn't need the LLM's "\n\n"
      // padding rendered as a visible blank line above it.
      if (renderMediaToken) preceding = preceding.replace(new RegExp(`[\\s${NBSP}]+$`), '');
      if (preceding) out.push({ type: 'text', value: preceding });
    }
    let cursor = m.index + m[0].length;
    if (isMediaToken) {
      if (renderMediaToken && !renderedMedia) {
        out.push({
          type: 'media',
          kind: m[1],
          title: (m[2] || '').trim(),
          subtitle: (m[3] || '').trim(),
        });
        renderedMedia = true;
        mediaState?.add('rendered');
        // Eat trailing sentence punct + any whitespace that follows the card,
        // for the same reason: card margin handles spacing, raw \n\n adds
        // a visible blank line on top.
        const tail = text.slice(cursor);
        const tm = tail.match(MEDIA_TRAILING_RE);
        if (tm && tm[0]) {
          cursor += tm[0].length;
          TOKEN_RE.lastIndex = cursor;
        }
      } else {
        const title = (m[2] || '').trim();
        if (title) out.push({ type: 'text', value: `《${title}》` });
        const tail = text.slice(cursor);
        if (renderMediaToken) {
          const whitespace = tail.match(new RegExp(`^[\\s${NBSP}]+`));
          if (whitespace && whitespace[0]) {
            cursor += whitespace[0].length;
            TOKEN_RE.lastIndex = cursor;
          }
        }
      }
    } else {
      out.push({ type: 'ref', id: m[4], label: m[5] });
    }
    last = cursor;
  }
  if (last < text.length) out.push({ type: 'text', value: text.slice(last) });
  return out;
}

function doFlash(el) {
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.add('ref-highlight');
  setTimeout(() => el.classList.remove('ref-highlight'), 2000);
}

function getActiveDayun() {
  const state = useAppStore.getState();
  const currentId = state?.currentId;
  const activeChartDayun = currentId ? state?.charts?.[currentId]?.dayun : null;

  if (Array.isArray(state?.dayun) && state.dayun.length) return state.dayun;
  if (Array.isArray(activeChartDayun)) return activeChartDayun;
  return [];
}

export function scrollAndFlash(id) {
  const el = document.querySelector(`[data-ref="${CSS.escape(id)}"]`);
  if (el) { doFlash(el); return true; }

  // liunian dead-link rescue: find which dayun step owns this year, expand it, then flash.
  if (id.startsWith('liunian.')) {
    const year = parseInt(id.split('.')[1]);
    if (isNaN(year)) { console.warn('[ref] no match:', id); return false; }
    // Find dayun cell that covers this year (via data-ref="dayun.N")
    const dayCells = Array.from(document.querySelectorAll('.dayun-cell[data-ref]'));
    // dayun step years are not stored in DOM attrs, so use the active chart data in store
    // to find which dayun step owns the requested liunian.
    const dayun = getActiveDayun();
    let targetIdx = -1;
    if (dayun && Array.isArray(dayun)) {
      targetIdx = dayun.findIndex(d => (d.years || []).some(y => y.year === year));
    }
    if (targetIdx < 0) {
      // heuristic: use startYear/endYear from cell data attributes if set
      for (const cell of dayCells) {
        const idx = parseInt(cell.dataset.idx);
        if (!isNaN(idx)) {
          // check in DOM if a chip for this year already exists after expand
          // Just try clicking the current-open step's sibling that covers the range
          // Without data, click the cell whose age-range might cover the year — unknown. Give up gracefully.
        }
      }
      console.warn('[ref] no match:', id); return false;
    }
    // Click dayun cell to expand it
    const cell = document.querySelector(`.dayun-cell[data-ref="dayun.${targetIdx}"]`);
    if (!cell) { console.warn('[ref] no match:', id); return false; }
    // Switch to timing view first
    const timingTab = Array.from(document.querySelectorAll('.view-item')).find(e => e.textContent.includes('流'));
    timingTab?.click();
    // If not already open (i.e. dayun body not visible), click to expand
    const bodyId = `dayun-step-body-${targetIdx}`;
    const existingBody = document.getElementById(bodyId);
    if (!existingBody || existingBody.style.display === 'none') {
      cell.click();
    }
    // Wait for React to render the liunian chips then flash
    const delay = existingBody && existingBody.style.display !== 'none' ? 50 : 800;
    setTimeout(() => {
      const target = document.querySelector(`[data-ref="${CSS.escape(id)}"]`);
      if (target) doFlash(target);
      else console.warn('[ref] liunian chip still not found after expand:', id);
    }, delay);
    return true;
  }

  console.warn('[ref] no match:', id);
  return false;
}
