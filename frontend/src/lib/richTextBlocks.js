function normalizeText(text) {
  return String(text || '').replace(/\r\n?/g, '\n');
}

function splitTableCells(line) {
  let raw = String(line || '').trim();
  if (!raw.includes('|')) return [];
  if (raw.startsWith('|')) raw = raw.slice(1);
  if (raw.endsWith('|')) raw = raw.slice(0, -1);

  const cells = [];
  let cell = '';
  for (let index = 0; index < raw.length; index += 1) {
    const ch = raw[index];
    if (ch === '\\' && raw[index + 1] === '|') {
      cell += '|';
      index += 1;
      continue;
    }
    if (ch === '|') {
      cells.push(cell.trim());
      cell = '';
      continue;
    }
    cell += ch;
  }
  cells.push(cell.trim());
  return cells;
}

function parseTableSeparator(line) {
  const cells = splitTableCells(line);
  if (cells.length < 2) return null;
  const align = [];
  for (const cell of cells) {
    const value = cell.replace(/\s+/g, '');
    if (!/^:?-{3,}:?$/.test(value)) return null;
    if (value.startsWith(':') && value.endsWith(':')) align.push('center');
    else if (value.endsWith(':')) align.push('right');
    else align.push('left');
  }
  return align;
}

function parseTableAt(lines, start) {
  const header = splitTableCells(lines[start]);
  const align = parseTableSeparator(lines[start + 1]);
  if (!align || header.length < 2 || align.length !== header.length) return null;

  const rows = [];
  let next = start + 2;
  while (next < lines.length) {
    const line = lines[next];
    if (!line.trim() || !line.includes('|')) break;
    const cells = splitTableCells(line);
    if (cells.length < 2) break;
    rows.push(header.map((_, i) => cells[i] || ''));
    next += 1;
  }

  return {
    block: {
      type: 'table',
      headers: header,
      rows,
      align,
    },
    next,
  };
}

function parseLinesToBlocks(lines) {
  const blocks = [];
  let paragraph = [];
  let quote = [];
  let listType = null;
  let listItems = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const blockText = paragraph.join('\n').trim();
    if (blockText) blocks.push({ type: 'p', text: blockText });
    paragraph = [];
  };
  const flushQuote = () => {
    if (!quote.length) return;
    const blockText = quote.join('\n').trim();
    if (blockText) blocks.push({ type: 'quote', text: blockText });
    quote = [];
  };
  const flushList = () => {
    if (!listItems.length) return;
    blocks.push({ type: listType, items: listItems });
    listItems = [];
    listType = null;
  };
  const flushAll = () => {
    flushParagraph();
    flushQuote();
    flushList();
  };

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (!line.trim()) {
      flushAll();
      continue;
    }

    if (i + 1 < lines.length) {
      const table = parseTableAt(lines, i);
      if (table) {
        flushAll();
        blocks.push(table.block);
        i = table.next - 1;
        continue;
      }
    }

    if (/^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      flushAll();
      blocks.push({ type: 'hr' });
      continue;
    }

    const heading = line.match(/^\s{0,3}#{1,6}\s+(.+)$/);
    if (heading) {
      flushAll();
      blocks.push({ type: 'heading', text: heading[1].trim() });
      continue;
    }

    const unordered = line.match(/^\s*(?:[-*+]|[·•])\s+(.+)$/);
    if (unordered) {
      flushParagraph();
      flushQuote();
      if (listType && listType !== 'ul') flushList();
      listType = 'ul';
      listItems.push(unordered[1].trim());
      continue;
    }

    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (ordered) {
      flushParagraph();
      flushQuote();
      if (listType && listType !== 'ol') flushList();
      listType = 'ol';
      listItems.push(ordered[1].trim());
      continue;
    }

    const quoteLine = line.match(/^\s*>\s?(.*)$/);
    if (quoteLine) {
      flushParagraph();
      flushList();
      quote.push(quoteLine[1]);
      continue;
    }

    flushQuote();
    flushList();
    paragraph.push(line);
  }

  flushAll();
  return blocks;
}

export function splitRichTextBlocks(text, options = {}) {
  const normalized = normalizeText(text);
  const lines = normalized.split('\n');
  const streaming = options.streaming === true;
  const hasPendingLine = streaming && normalized && !normalized.endsWith('\n');

  if (!hasPendingLine) return parseLinesToBlocks(lines);

  const pendingLine = lines.pop();
  const blocks = parseLinesToBlocks(lines);
  const pendingText = String(pendingLine || '').trim();
  if (pendingText) {
    blocks.push({ type: 'p', text: pendingText, streaming: true });
  }
  return blocks;
}
