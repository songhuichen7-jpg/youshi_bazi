import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {
  getFallbackPalette,
  getFallbackInitial,
  _PALETTE_FOR_TEST,
} from '../src/lib/avatarFallback.js';

test('getFallbackPalette returns one of the 6 palette entries', () => {
  const got = getFallbackPalette('abc');
  assert.ok(_PALETTE_FOR_TEST.some(p => p.bg === got.bg && p.ink === got.ink));
});

test('getFallbackPalette is stable across calls', () => {
  const a = getFallbackPalette('user-001');
  const b = getFallbackPalette('user-001');
  assert.deepEqual(a, b);
});

test('different seeds usually yield different palette entries', () => {
  // not a hard guarantee due to mod 6 collisions, but with these 6 inputs
  // expect at least 4 distinct entries.
  const seeds = ['a', 'b', 'c', 'd', 'e', 'f'];
  const set = new Set(seeds.map(s => getFallbackPalette(s).bg));
  assert.ok(set.size >= 4, `expected ≥4 distinct, got ${set.size}`);
});

test('getFallbackInitial returns first char (CJK-aware)', () => {
  assert.equal(getFallbackInitial('小夜灯'), '小');
  assert.equal(getFallbackInitial(''), '?');
  assert.equal(getFallbackInitial(null), '?');
  assert.equal(getFallbackInitial('  橡子  '), '橡');
});

test('emoji/extended seeds do not crash', () => {
  // surrogate pairs etc.
  const got = getFallbackPalette('🎄user');
  assert.ok(got && got.bg);
});

test('AvatarBadge has onError handler that switches to fallback', () => {
  const src = fs.readFileSync(
    new URL('../src/components/AvatarBadge.jsx', import.meta.url),
    'utf8',
  );
  // The img must have an onError that flips a state to fallback
  assert.match(src, /onError/);
  assert.match(src, /imgFailed/);
});

test('HepanList threads avatarUrl to AvatarBadge for both A and B', () => {
  const src = fs.readFileSync(
    new URL('../src/components/hepan/HepanList.jsx', import.meta.url),
    'utf8',
  );
  assert.match(src, /avatarUrl=\{item\.a_avatar_url\}/);
  assert.match(src, /avatarUrl=\{item\.b_avatar_url\}/);
});

test('HepanScreen threads avatarUrl on the inviter avatar', () => {
  const src = fs.readFileSync(
    new URL('../src/components/hepan/HepanScreen.jsx', import.meta.url),
    'utf8',
  );
  assert.match(src, /avatarUrl=\{hepan\.a\?\.avatar_url\}/);
});
