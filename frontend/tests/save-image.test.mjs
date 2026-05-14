import test from 'node:test';
import assert from 'node:assert/strict';
import { isMobileUserAgent } from '../src/lib/saveImage.js';

test('iOS detected as mobile', () => {
  assert.equal(isMobileUserAgent('Mozilla/5.0 (iPhone; CPU iPhone OS 15_0)'), true);
});

test('Android detected as mobile', () => {
  assert.equal(isMobileUserAgent('Mozilla/5.0 (Linux; Android 11)'), true);
});

test('iPad detected as mobile', () => {
  assert.equal(isMobileUserAgent('Mozilla/5.0 (iPad; CPU OS 15_0)'), true);
});

test('desktop Chrome not mobile', () => {
  assert.equal(isMobileUserAgent('Mozilla/5.0 (X11; Linux x86_64) Chrome/100'), false);
});

test('desktop Safari not mobile', () => {
  assert.equal(isMobileUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/604'), false);
});
