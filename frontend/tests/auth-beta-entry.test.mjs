import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

test('beta auth screen keeps the phone login form hidden while config is loading', () => {
  const source = fs.readFileSync(new URL('../src/components/AuthScreen.jsx', import.meta.url), 'utf8');

  assert.match(source, /const \[guestLoginEnabled,\s*setGuestLoginEnabled\]\s*=\s*useState\(null\)/);
  assert.match(source, /guestLoginEnabled\s*===\s*null/);
  assert.match(source, /return \(\s*<div className="screen active">[\s\S]*?有 时 · 内 测[\s\S]*?<\/div>\s*\)/);
  assert.match(source, /const showBetaEntry = guestLoginEnabled === true && !showFullAuth/);
});
