import test from 'node:test';
import assert from 'node:assert/strict';

import { buildPersonaDisplay, buildVerdictDisplay } from '../src/lib/classics.js';

test('buildPersonaDisplay returns null for null/empty input', () => {
  assert.equal(buildPersonaDisplay(null), null);
  assert.equal(buildPersonaDisplay({}), null);
  assert.equal(buildPersonaDisplay({ quote: '   ' }), null);
});

test('buildPersonaDisplay normalizes a full payload', () => {
  const out = buildPersonaDisplay({
    quote: '甲子日元，生于孟春。 ',
    plain: '木火得位 ',
    book: '滴天髓',
    chapter: '性情',
    section: '命例 1',
    tier: 'case',
    fit_note: '日干甲、月令寅',
  });
  assert.equal(out.quote, '甲子日元，生于孟春。');
  assert.equal(out.plain, '木火得位');
  assert.equal(out.tier, 'case');
  assert.equal(out.section, '命例 1');
});

test('buildPersonaDisplay coerces invalid tier to general', () => {
  const out = buildPersonaDisplay({
    quote: 'x', plain: 'y', book: 'z', chapter: 'w', tier: 'mystery', fit_note: 'n',
  });
  assert.equal(out.tier, 'general');
});

test('buildVerdictDisplay returns null on missing quote', () => {
  assert.equal(buildVerdictDisplay(null), null);
  assert.equal(buildVerdictDisplay({ book: '三命通会' }), null);
});

test('buildVerdictDisplay normalizes a full payload', () => {
  const out = buildVerdictDisplay({
    quote: '正官透干、印星护身，主清贵',
    book: '三命通会',
    chapter: '论命格高低',
  });
  assert.equal(out.quote, '正官透干、印星护身，主清贵');
  assert.equal(out.book, '三命通会');
});
