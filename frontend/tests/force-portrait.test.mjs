import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

import { buildForcePortrait, classifyForceBand } from '../src/lib/forcePortrait.js';
import { GLOSSARY } from '../src/lib/baziGlossary.js';


test('buildForcePortrait: 七杀压顶的盘给出"主导 · 次之 · 缺位" headline 和人话 reading', () => {
  // 来自截图真实数据：七杀 10 / 偏财 4.1 / 正财 2.9 / 比肩 0 / 食神 0
  const force = [
    { name: '比肩', val: 0.0 },
    { name: '劫财', val: 0.9 },
    { name: '食神', val: 0.0 },
    { name: '伤官', val: 0.9 },
    { name: '正财', val: 2.9 },
    { name: '偏财', val: 4.1 },
    { name: '正官', val: 0.7 },
    { name: '七杀', val: 10.0 },
    { name: '正印', val: 1.8 },
    { name: '偏印', val: 0.7 },
  ];
  const portrait = buildForcePortrait(force);

  assert.ok(portrait, '应返回 portrait 对象');
  // headline 列出"主导 / 次之 / 缺位"三段
  assert.match(portrait.headline, /七杀主导/);
  assert.match(portrait.headline, /偏财次之/);
  assert.match(portrait.headline, /(比肩|食神)缺位/);
  // reading 是一行人话，含主导项的"高"语义 + 缺位项的"低"语义
  assert.match(portrait.reading, /(压力|外部)/);
  // 两段以"、"连，"。"收尾
  assert.match(portrait.reading, /^[^、。]+、[^。]+。$/);
});


test('buildForcePortrait: 力量分布相对均衡时，缺位段被省略', () => {
  // 全部 1-3 之间，无人缺位
  const force = [
    { name: '比肩', val: 2.0 },
    { name: '劫财', val: 2.0 },
    { name: '食神', val: 3.0 },
    { name: '伤官', val: 1.5 },
    { name: '正财', val: 2.5 },
    { name: '偏财', val: 2.5 },
    { name: '正官', val: 1.2 },
    { name: '七杀', val: 1.0 },
    { name: '正印', val: 1.8 },
    { name: '偏印', val: 1.0 },
  ];
  const portrait = buildForcePortrait(force);

  assert.ok(portrait);
  assert.match(portrait.headline, /食神/); // top = 食神 3.0
  // 没人 val < 1，应不出现"缺位"
  assert.doesNotMatch(portrait.headline, /缺位/);
});


test('buildForcePortrait: 空数据或全 0 时返回 null（不渲染画像）', () => {
  assert.equal(buildForcePortrait([]), null);
  assert.equal(buildForcePortrait(null), null);
  assert.equal(buildForcePortrait(undefined), null);
  assert.equal(
    buildForcePortrait([
      { name: '比肩', val: 0 },
      { name: '七杀', val: 0 },
    ]),
    null,
  );
});


test('classifyForceBand: <1 缺 / 1-5 平 / >=5 旺', () => {
  assert.equal(classifyForceBand(0), 'low');
  assert.equal(classifyForceBand(0.9), 'low');
  assert.equal(classifyForceBand(1), 'mid');
  assert.equal(classifyForceBand(4.9), 'mid');
  assert.equal(classifyForceBand(5), 'high');
  assert.equal(classifyForceBand(10), 'high');
  // 兜底
  assert.equal(classifyForceBand(null), 'low');
  assert.equal(classifyForceBand(undefined), 'low');
});


test('Force component renders three-color bar bands + dominant badge', () => {
  const source = fs.readFileSync(new URL('../src/components/Force.jsx', import.meta.url), 'utf8');

  // 仍然调 buildForcePortrait 拿 topName 给"主导"角标，但已不渲染
  // 文字画像块（用户嫌跟周边视觉太突兀，已删除）
  assert.match(source, /buildForcePortrait/);
  assert.match(source, /classifyForceBand/);
  assert.match(source, /force-bar-\$\{band\}/);
  assert.match(source, /force-row-\$\{band\}/);
  assert.match(source, /is-dominant/);
  assert.match(source, /force-dominant-badge/);
  // 画像 JSX 已下线 — 不应再出现
  assert.doesNotMatch(source, /className="force-portrait"/);
  assert.doesNotMatch(source, /force-portrait-headline/);
});


test('every glossary entry has a plain reading + tech desc, so tooltip never shows half a card', () => {
  // 上层（plain）和下层（desc）必须都齐全 — 否则新 tooltip 在某条 hover 时
  // 会缺一段，视觉断层。
  const entries = Object.entries(GLOSSARY);
  assert.ok(entries.length >= 30, '词条数量 >= 30');
  for (const [key, value] of entries) {
    assert.ok(value.term && value.term.length > 0, `${key}: term 缺失`);
    assert.ok(value.plain && value.plain.length > 0, `${key}: plain 缺失`);
    assert.ok(value.desc && value.desc.length > 0, `${key}: desc 缺失`);
  }
});


test('TooltipLayer renders two-tier content (plain + divider + desc) and tracks placement', () => {
  const source = fs.readFileSync(new URL('../src/components/TooltipLayer.jsx', import.meta.url), 'utf8');
  const css = fs.readFileSync(new URL('../src/index.css', import.meta.url), 'utf8');

  // 双层 DOM 节点 + divider
  assert.match(source, /bz-tooltip-term/);
  assert.match(source, /bz-tooltip-plain/);
  assert.match(source, /bz-tooltip-divider/);
  assert.match(source, /bz-tooltip-desc/);
  // 真实 getBoundingClientRect 测尺寸（不再用估算）
  assert.match(source, /getBoundingClientRect/);
  // 摆位通过 data-placement 切换上下
  assert.match(source, /data-placement|dataset\.placement/);
  // 箭头 X 通过 CSS 变量驱动，随 trigger 中心走
  assert.match(source, /--bz-tooltip-arrow-x/);

  // CSS：paper-tone + 双三角 + 上下两种 placement
  assert.match(css, /\.bz-tooltip\s*\{[^}]*background:\s*#fbf6e9/);
  assert.match(css, /\.bz-tooltip\[data-placement="above"\]::before/);
  assert.match(css, /\.bz-tooltip\[data-placement="below"\]::before/);
  // 可发现性：data-tip 默认 help cursor
  assert.match(css, /\[data-tip\]\s*\{[^}]*cursor:\s*help/);
});
