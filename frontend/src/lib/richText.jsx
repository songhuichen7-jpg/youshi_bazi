/**
 * Parse a plain-text segment containing inline markdown (**bold**, *italic*, `code`)
 * and return an array of React nodes.
 */
export function renderInlineMd(text, baseKey) {
  // Pattern: **bold** | *italic* | `code`
  const pattern = /(\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`)/gs;
  const nodes = [];
  let last = 0;
  let k = baseKey;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) {
      nodes.push(text.slice(last, match.index));
    }
    if (match[0].startsWith('**')) {
      nodes.push(<strong key={k++}>{match[2]}</strong>);
    } else if (match[0].startsWith('*')) {
      nodes.push(<em key={k++}>{match[3]}</em>);
    } else {
      nodes.push(<code key={k++}>{match[4]}</code>);
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

/**
 * Convert a markdown text block into React nodes.
 * Handles: **bold**, *italic*, `code`, headings, blockquote markers, and bullets.
 */
export function renderMd(text) {
  if (!text) return null;
  const processed = String(text)
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/^>\s*/gm, '')
    .replace(/^[-*+]\s+/gm, '· ');

  return renderInlineMd(processed, 0);
}
