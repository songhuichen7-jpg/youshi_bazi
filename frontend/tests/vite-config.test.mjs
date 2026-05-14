import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

test('vite dev server listens on IPv4 localhost as well as localhost', () => {
  const source = fs.readFileSync(new URL('../vite.config.js', import.meta.url), 'utf8');

  assert.match(source, /host:\s*['"]0\.0\.0\.0['"]/);
});

test('vite proxy target can point at an alternate backend for verification', () => {
  const source = fs.readFileSync(new URL('../vite.config.js', import.meta.url), 'utf8');

  assert.match(source, /env\.BACKEND_URL/);
  assert.match(source, /backendTarget/);
});
