import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('route changes emit page_view analytics outside admin', () => {
  const source = readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8');
  assert.match(source, /trackPageView/);
  assert.match(source, /trackPagePerformance/);
  assert.match(source, /startsWith\('\/admin'\)/);
});

test('app birth form tracks chart success and failure', () => {
  const source = readFileSync(new URL('../src/components/FormScreen.jsx', import.meta.url), 'utf8');
  assert.match(source, /chart_create_success/);
  assert.match(source, /chart_create_failed/);
});

test('card birth flow tracks generated share slug', () => {
  const source = readFileSync(new URL('../src/components/card\/LandingScreen.jsx', import.meta.url), 'utf8');
  assert.match(source, /chart_create_success/);
  assert.match(source, /share_slug/);
});
