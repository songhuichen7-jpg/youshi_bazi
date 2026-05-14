import test from 'node:test';
import assert from 'node:assert/strict';
import { buildPartnerBirthPayload } from '../src/components/hepan/partnerBirthValidation.js';

test('rejects empty date', () => {
  assert.throws(() => buildPartnerBirthPayload({ date: '' }), /出生日期/);
});

test('rejects malformed date', () => {
  assert.throws(() => buildPartnerBirthPayload({ date: '20260507' }), /生日格式/);
});

test('rejects out-of-range year', () => {
  assert.throws(
    () => buildPartnerBirthPayload({ date: '1899-01-01', hourUnknown: true }),
    /1900-2100/,
  );
});

test('rejects Feb 30', () => {
  assert.throws(
    () => buildPartnerBirthPayload({ date: '2024-02-30', hourUnknown: true }),
    /没有这一天/,
  );
});

test('hourUnknown true skips time validation', () => {
  const out = buildPartnerBirthPayload({
    date: '2000-05-07', hourUnknown: true, city: '', gender: '',
  });
  assert.equal(out.hour, -1);
  assert.equal(out.minute, 0);
});

test('parses normal payload', () => {
  const out = buildPartnerBirthPayload({
    date: '2000-05-07', time: '14:30', hourUnknown: false,
    city: '  上海  ', gender: 'female', nickname: '小夜灯',
  });
  assert.equal(out.year, 2000);
  assert.equal(out.month, 5);
  assert.equal(out.day, 7);
  assert.equal(out.hour, 14);
  assert.equal(out.minute, 30);
  assert.equal(out.gender, 'female');
  assert.equal(out.city, '上海');
});

test('blank city normalized to null', () => {
  const out = buildPartnerBirthPayload({
    date: '2000-05-07', hourUnknown: true, city: '   ', gender: '',
  });
  assert.equal(out.city, null);
  assert.equal(out.gender, null);
});
