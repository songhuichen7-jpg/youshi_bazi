import test from 'node:test';
import assert from 'node:assert/strict';
import { getAnonymousId } from '../src/lib/anonymousId.js';

test('generates new id when cookie missing', () => {
  const cookieStore = { value: '' };
  const id = getAnonymousId({
    readCookie: () => cookieStore.value,
    writeCookie: v => cookieStore.value = v,
  });
  assert.match(id, /^a_[a-z0-9]{14}$/);
  assert.match(cookieStore.value, /youshi_aid=a_[a-z0-9]{14}/);
});

test('returns existing id when cookie present and refreshes expiry', () => {
  const cookieStore = { value: 'youshi_aid=a_existing123456' };
  let wrote = '';
  const id = getAnonymousId({
    readCookie: () => cookieStore.value,
    writeCookie: v => wrote = v,
  });
  assert.equal(id, 'a_existing123456');
  assert.match(wrote, /youshi_aid=a_existing123456/);
  assert.match(wrote, /Max-Age=/);
});

test('ignores malformed cookie', () => {
  const cookieStore = { value: 'other=foo; youshi_aid=BADFORMAT' };
  let wrote = '';
  const id = getAnonymousId({
    readCookie: () => cookieStore.value,
    writeCookie: v => wrote = v,
  });
  assert.match(id, /^a_[a-z0-9]{14}$/);
  assert.notEqual(id, 'BADFORMAT');
});
