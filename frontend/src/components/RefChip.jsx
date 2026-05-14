import { parseRef } from '../lib/parseRef';
import { renderInlineMd } from '../lib/richText.jsx';
import { splitRichTextBlocks } from '../lib/richTextBlocks.js';
import { MediaCard } from './MediaCard';

export function RefChip({ id, label }) {
  const onClick = (e) => {
    e.preventDefault();
    window.dispatchEvent(new CustomEvent('bazi:ref-click', { detail: { id } }));
  };
  return (
    <a
      href="#"
      className="ref-chip"
      data-ref-link={id}
      onClick={onClick}
      title={id}
    >{label}</a>
  );
}

function renderInlineSegments(segs, keyPrefix) {
  let textKey = 0;
  return segs.flatMap((s, i) => {
    if (s.type === 'ref') {
      return [<RefChip key={`${keyPrefix}-ref-${i}`} id={s.id} label={s.label} />];
    }
    if (s.type === 'media') {
      return [
        <MediaCard
          key={`${keyPrefix}-media-${i}`}
          kind={s.kind}
          title={s.title}
          subtitle={s.subtitle}
        />,
      ];
    }
    return renderInlineMd(String(s.value || ''), textKey++ * 1000);
  });
}

function renderFlowSegments(segs, keyPrefix) {
  const nodes = [];
  let inlineSegs = [];
  let chunk = 0;

  const flushInline = () => {
    const hasText = inlineSegs.some((s) => s.type === 'ref' || String(s.value || '').trim());
    if (!hasText) {
      inlineSegs = [];
      return;
    }
    nodes.push(
      <p className="rich-md-p" key={`${keyPrefix}-p-${chunk++}`}>
        {renderInlineSegments(inlineSegs, `${keyPrefix}-inline-${chunk}`)}
      </p>,
    );
    inlineSegs = [];
  };

  segs.forEach((s, i) => {
    if (s.type !== 'media') {
      inlineSegs.push(s);
      return;
    }
    flushInline();
    nodes.push(
      <MediaCard
        key={`${keyPrefix}-media-${i}`}
        kind={s.kind}
        title={s.title}
        subtitle={s.subtitle}
      />,
    );
  });
  flushInline();

  if (nodes.length === 1) return nodes[0];
  return <div className="rich-md-flow" key={`${keyPrefix}-flow`}>{nodes}</div>;
}

function renderParagraph(text, context, keyPrefix, mediaState) {
  const segs = parseRef(text, { context, mediaState });
  if (!segs.length) return null;
  return renderFlowSegments(segs, keyPrefix);
}

function renderHeading(text, context, keyPrefix, mediaState) {
  const segs = parseRef(text, { context, mediaState });
  if (!segs.length) return null;
  return (
    <h3 className="rich-md-heading" key={`${keyPrefix}-heading`}>
      {renderInlineSegments(segs, `${keyPrefix}-heading-inline`)}
    </h3>
  );
}

function renderQuote(text, context, keyPrefix, mediaState) {
  const segs = parseRef(text, { context, mediaState });
  if (!segs.length) return null;
  return (
    <blockquote className="rich-md-quote" key={`${keyPrefix}-quote`}>
      {renderInlineSegments(segs, `${keyPrefix}-quote-inline`)}
    </blockquote>
  );
}

function renderList(items, type, context, keyPrefix, mediaState) {
  if (type === 'ol') {
    return (
      <ol className="rich-md-list" key={`${keyPrefix}-ol`}>
        {items.map((itemText, i) => {
          const itemSegs = parseRef(itemText, { context, mediaState });
          return (
            <li key={`${keyPrefix}-ol-item-${i}`}>
              {renderInlineSegments(itemSegs, `${keyPrefix}-ol-inline-${i}`)}
            </li>
          );
        })}
      </ol>
    );
  }

  return (
    <ul className="rich-md-list" key={`${keyPrefix}-ul`}>
      {items.map((itemText, i) => {
        const itemSegs = parseRef(itemText, { context, mediaState });
        return (
          <li key={`${keyPrefix}-ul-item-${i}`}>
            {renderInlineSegments(itemSegs, `${keyPrefix}-ul-inline-${i}`)}
          </li>
        );
      })}
    </ul>
  );
}

function renderTable(block, context, keyPrefix, mediaState) {
  const alignStyle = (i) => (
    block.align?.[i] ? { textAlign: block.align[i] } : undefined
  );

  return (
    <div className="rich-md-table-wrap" key={`${keyPrefix}-table-wrap`}>
      <table className="rich-md-table">
        <thead>
          <tr>
            {block.headers.map((cell, i) => (
              <th key={`${keyPrefix}-th-${i}`} style={alignStyle(i)}>
                {renderInlineSegments(
                  parseRef(cell, { context, mediaState }),
                  `${keyPrefix}-th-inline-${i}`,
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row, rowIdx) => (
            <tr key={`${keyPrefix}-tr-${rowIdx}`}>
              {row.map((cell, cellIdx) => (
                <td key={`${keyPrefix}-td-${rowIdx}-${cellIdx}`} style={alignStyle(cellIdx)}>
                  {renderInlineSegments(
                    parseRef(cell, { context, mediaState }),
                    `${keyPrefix}-td-inline-${rowIdx}-${cellIdx}`,
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderRichTextBlocks(text, context, options = {}) {
  const mediaState = new Set();
  return splitRichTextBlocks(text, { streaming: options.streaming === true })
    .map((block, key) => {
      const keyPrefix = `block-${key}`;
      if (block.type === 'heading') return renderHeading(block.text, context, keyPrefix, mediaState);
      if (block.type === 'quote') return renderQuote(block.text, context, keyPrefix, mediaState);
      if (block.type === 'hr') return <hr className="rich-md-hr" key={`${keyPrefix}-hr`} />;
      if (block.type === 'ol' || block.type === 'ul') {
        return renderList(block.items, block.type, context, keyPrefix, mediaState);
      }
      if (block.type === 'table') return renderTable(block, context, keyPrefix, mediaState);
      return renderParagraph(block.text, context, keyPrefix, mediaState);
    })
    .filter(Boolean);
}

/** Render a string that may contain [[ref|label]] or artifact markers
 *  ([[song:…]], [[flower:…]], etc.) as a mix of text + RefChip + MediaCard.
 *  ``context`` (e.g. the preceding user question) lets parseRef rescue
 *  《XX》 → media token when the question was "用一首歌/一部电影 形容…"
 *  but the LLM fell back to 书名号 instead of the structured token. */
export function RichText({ text, context, streaming }) {
  const blocks = renderRichTextBlocks(text, context, { streaming });
  if (!blocks.length) return null;
  return <div className="rich-md">{blocks}</div>;
}
