import test from 'node:test';
import assert from 'node:assert/strict';

import { chartResponseToEntry } from '../src/lib/chartUi.js';

test('chartResponseToEntry maps analyzer output into force, guards, and meta fields', () => {
  const entry = chartResponseToEntry({
    chart: {
      id: 'chart-1',
      label: '测试盘',
      created_at: '2026-04-19T00:00:00Z',
      updated_at: '2026-04-19T00:00:00Z',
      birth_input: {
        year: 1993,
        month: 7,
        day: 15,
        hour: 14,
        minute: 30,
        gender: 'male',
        city: '长沙',
      },
      paipan: {
        sizhu: { year: '癸酉', month: '己未', day: '丁酉', hour: '丁未' },
        rizhu: '丁',
        cangGan: {},
        shishen: {},
        force: {
          dayStrength: '身弱',
          sameSideScore: 4.3,
          otherSideScore: 16,
          scores: {
            比肩: 4.4,
            劫财: 0,
            食神: 10,
            伤官: 0,
            正财: 0,
            偏财: 4.4,
            正官: 0,
            七杀: 3.3,
            正印: 0,
            偏印: 0.3,
          },
        },
        geJu: {
          mainCandidate: { name: '食神格' },
          decisionNote: '四库月 未，己/丁 透干',
        },
        geju: '食神格',
        yongshen: '比劫（帮身）',
        zhiRelations: {
          liuHe: [{ a: '子', b: '丑', wuxing: '土' }],
          chong: [{ a: '戌', b: '辰' }],
          sanHe: [{ zhi: ['申', '子', '辰'], wuxing: '水', type: 'full' }],
          banHe: [{ zhi: ['申', '子'], wuxing: '水' }],
          sanHui: [{ zhi: ['寅', '卯', '辰'], wuxing: '木', dir: '东' }],
        },
        notes: [
          {
            type: 'pair_mismatch',
            message: '比劫 组中 比肩 (4.4) vs 劫财 (0) 强度差异大，分析时不能笼统称"比劫旺/弱"',
          },
        ],
      },
    },
  });

  assert.equal(entry.force.length, 10);
  assert.deepEqual(entry.force[0], { name: '比肩', val: 4.4 });
  assert.deepEqual(entry.force[2], { name: '食神', val: 10 });
  assert.deepEqual(entry.guards, [
    { type: 'pair_mismatch', note: '比劫 组中 比肩 (4.4) vs 劫财 (0) 强度差异大，分析时不能笼统称"比劫旺/弱"' },
    { type: 'liuhe', note: '子丑 六合 化 土' },
    { type: 'chong', note: '戌辰 相冲' },
    { type: 'sanhe', note: '三合 申子辰 化 水' },
    { type: 'banhe', note: '半合 申子 → 水' },
    { type: 'sanhui', note: '三会 寅卯辰 东方木' },
  ]);
  assert.equal(entry.meta.dayStrength, '身弱');
  assert.equal(entry.meta.geju, '食神格');
  assert.equal(entry.meta.gejuNote, '四库月 未，己/丁 透干');
  assert.equal(entry.meta.yongshen, '比劫（帮身）');
  assert.equal(entry.meta.sameSideScore, 4.3);
  assert.equal(entry.meta.otherSideScore, 16);
});

test('chartResponseToEntry deduplicates repeated sanhe-style guard relations', () => {
  const entry = chartResponseToEntry({
    chart: {
      id: 'chart-3',
      created_at: '2026-04-19T00:00:00Z',
      updated_at: '2026-04-19T00:00:00Z',
      birth_input: {},
      paipan: {
        sizhu: { day: '甲子' },
        cangGan: {},
        shishen: {},
        zhiRelations: {
          sanHe: [
            { zhi: ['申', '子', '辰'], wuxing: '水', type: 'full' },
            { zhi: ['申', '子', '辰'], wuxing: '水', type: 'full' },
          ],
          banHe: [
            { zhi: ['申', '子'], wuxing: '水' },
            { zhi: ['申', '子'], wuxing: '水' },
          ],
          sanHui: [
            { zhi: ['亥', '子', '丑'], wuxing: '水', dir: '北' },
            { zhi: ['亥', '子', '丑'], wuxing: '水', dir: '北' },
          ],
        },
      },
    },
  });

  assert.deepEqual(entry.guards, [
    { type: 'sanhe', note: '三合 申子辰 化 水' },
    { type: 'banhe', note: '半合 申子 → 水' },
    { type: 'sanhui', note: '三会 亥子丑 北方水' },
  ]);
});

test('chartResponseToEntry keeps force and guards empty when analyzer fields are absent', () => {
  const entry = chartResponseToEntry({
    chart: {
      id: 'chart-2',
      created_at: '2026-04-19T00:00:00Z',
      updated_at: '2026-04-19T00:00:00Z',
      birth_input: {},
      paipan: {
        sizhu: { day: '甲戌' },
        cangGan: {},
        shishen: {},
      },
    },
  });

  assert.deepEqual(entry.force, []);
  assert.deepEqual(entry.guards, []);
  assert.equal(entry.meta.dayStrength, '');
  assert.equal(entry.meta.geju, '');
  assert.equal(entry.meta.yongshen, '');
});
