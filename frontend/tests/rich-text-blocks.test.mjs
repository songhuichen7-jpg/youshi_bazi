import test from 'node:test';
import assert from 'node:assert/strict';

import { splitRichTextBlocks } from '../src/lib/richTextBlocks.js';

test('streaming keeps an incomplete markdown line as a stable paragraph', () => {
  const streaming = splitRichTextBlocks('1. 核心判断', { streaming: true });
  assert.deepEqual(streaming, [
    { type: 'p', text: '1. 核心判断', streaming: true },
  ]);

  const settled = splitRichTextBlocks('1. 核心判断', { streaming: false });
  assert.deepEqual(settled, [
    { type: 'ol', items: ['核心判断'] },
  ]);
});

test('streaming parses completed list lines and leaves only the active line plain', () => {
  const blocks = splitRichTextBlocks('1. 第一层\n2. 第二层', { streaming: true });

  assert.deepEqual(blocks, [
    { type: 'ol', items: ['第一层'] },
    { type: 'p', text: '2. 第二层', streaming: true },
  ]);
});

test('streaming treats a trailing newline as a completed markdown block', () => {
  const blocks = splitRichTextBlocks('1. 第一层\n', { streaming: true });

  assert.deepEqual(blocks, [
    { type: 'ol', items: ['第一层'] },
  ]);
});

test('horizontal rules render as separators instead of raw markdown text', () => {
  const blocks = splitRichTextBlocks('上段\n\n---\n\n下段');

  assert.deepEqual(blocks, [
    { type: 'p', text: '上段' },
    { type: 'hr' },
    { type: 'p', text: '下段' },
  ]);
});

test('markdown table rows become a table block', () => {
  const blocks = splitRichTextBlocks([
    '前文',
    '',
    '| 年份 | 主题 | 强度 |',
    '| --- | :---: | ---: |',
    '| 2026 | **推进** | 8 |',
    '| 2027 | 保守\\|观察 | 6 |',
    '',
    '后文',
  ].join('\n'));

  assert.deepEqual(blocks, [
    { type: 'p', text: '前文' },
    {
      type: 'table',
      headers: ['年份', '主题', '强度'],
      rows: [
        ['2026', '**推进**', '8'],
        ['2027', '保守|观察', '6'],
      ],
      align: ['left', 'center', 'right'],
    },
    { type: 'p', text: '后文' },
  ]);
});
