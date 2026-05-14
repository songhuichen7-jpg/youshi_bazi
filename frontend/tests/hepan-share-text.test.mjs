import test from 'node:test';
import assert from 'node:assert/strict';
import { composeHepanShareText } from '../src/lib/hepanShareText.js';

test('composes "{name} 邀请你来合个盘 — {url}" for real nickname', () => {
  const out = composeHepanShareText('小夜灯', 'http://example.com/hepan/abc');
  assert.equal(out, '小夜灯 邀请你来合个盘 — http://example.com/hepan/abc');
});

test('falls back to "想跟你合个盘 — {url}" when inviter is empty', () => {
  const out = composeHepanShareText('', 'http://x/hepan/y');
  assert.equal(out, '想跟你合个盘 — http://x/hepan/y');
});

test('falls back when inviter is the literal "游客"', () => {
  const out = composeHepanShareText('游客', 'http://x/hepan/y');
  assert.equal(out, '想跟你合个盘 — http://x/hepan/y');
});

test('trims whitespace around inviter', () => {
  const out = composeHepanShareText('  小夜灯  ', 'http://x/hepan/y');
  assert.equal(out, '小夜灯 邀请你来合个盘 — http://x/hepan/y');
});

test('handles null/undefined inviter', () => {
  assert.equal(composeHepanShareText(null, 'http://x/y').includes('想跟你合个盘'), true);
  assert.equal(composeHepanShareText(undefined, 'http://x/y').includes('想跟你合个盘'), true);
});
