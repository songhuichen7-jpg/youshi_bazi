import test from 'node:test';
import assert from 'node:assert/strict';

import { buildDayunPanel, buildLiunianPanel } from '../src/lib/timingPanels.js';


test('buildDayunPanel turns a step into a readable overview card model', () => {
  const panel = buildDayunPanel(
    { age: 18, gz: '戊午', ss: '偏财/伤官' },
    '这步戊午大运，压力先起。\n\n中段开始转成硬碰硬的成长。\n\n末段会有明显转折。',
  );

  assert.deepEqual(panel, {
    kicker: '大运总览',
    title: '戊午大运',
    meta: '18岁起 · 偏财/伤官',
    paragraphs: [
      '这步戊午大运，压力先起。',
      '中段开始转成硬碰硬的成长。',
      '末段会有明显转折。',
    ],
  });
});


test('buildLiunianPanel formats a year note as a nested reading card', () => {
  const panel = buildLiunianPanel(
    { year: 2014, gz: '甲午' },
    '这一年火势上扬。\n\n做事容易急，但推进速度快。',
  );

  assert.deepEqual(panel, {
    kicker: '流年细看',
    title: '2014 甲午',
    meta: null,
    paragraphs: [
      '这一年火势上扬。',
      '做事容易急，但推进速度快。',
    ],
  });
});
