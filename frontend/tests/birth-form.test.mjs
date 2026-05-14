// frontend/tests/birth-form.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { validateBirthInput } from '../src/components/card/birthValidation.js';

test('valid birth passes', () => {
  assert.equal(validateBirthInput({ year: '1998', month: '07', day: '15' }).ok, true);
});

test('missing year fails', () => {
  const r = validateBirthInput({ year: '', month: '07', day: '15' });
  assert.equal(r.ok, false);
  assert.match(r.error, /年份|完整/);
});

test('year out of range fails', () => {
  const r = validateBirthInput({ year: '1800', month: '01', day: '01' });
  assert.equal(r.ok, false);
  assert.match(r.error, /1900/);
});

test('invalid day for month fails', () => {
  const r = validateBirthInput({ year: '2001', month: '02', day: '30' });
  assert.equal(r.ok, false);
});

test('leap year Feb 29 passes', () => {
  assert.equal(validateBirthInput({ year: '2000', month: '02', day: '29' }).ok, true);
});

test('non-leap year Feb 29 fails', () => {
  assert.equal(validateBirthInput({ year: '2001', month: '02', day: '29' }).ok, false);
});

test('app birth form starts empty and shows a subtle helper instead of sample data', () => {
  const source = fs.readFileSync(new URL('../src/components/FormScreen.jsx', import.meta.url), 'utf8');

  assert.match(source, /useState\(birthInfo\?\.date \|\| ''\)/);
  assert.match(source, /useState\(birthInfo\?\.time \|\| ''\)/);
  assert.match(source, /useState\(birthInfo\?\.city \|\| ''\)/);
  assert.match(source, /useState\(birthInfo\?\.gender \|\| ''\)/);
  assert.match(source, /请选择性别/);
  assert.match(source, /form-subtle-hint/);
  assert.doesNotMatch(source, /1993-07-15/);
  assert.doesNotMatch(source, /14:30/);
  assert.doesNotMatch(source, /birthInfo\?\.city \|\| '长沙'/);
});
