import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

test('brand logo component exposes the sundial mark and wordmark variants', () => {
  const source = fs.readFileSync(new URL('../src/components/brand/BrandLogo.jsx', import.meta.url), 'utf8');

  assert.match(source, /export function YoushiMark/);
  assert.match(source, /export function BrandLogo/);
  assert.match(source, /M50 15V85/);
  assert.match(source, /M50 50L73 36/);
  assert.match(source, /有时/);
  assert.match(source, /YOUSHI/);
});

test('landing page uses the brand logo in the first viewport and footer', () => {
  const source = fs.readFileSync(new URL('../src/components/landing/LandingHome.jsx', import.meta.url), 'utf8');

  assert.match(source, /import \{ BrandLogo \} from '\.\.\/brand\/BrandLogo\.jsx'/);
  assert.match(source, /className="landing-brand-masthead"/);
  assert.match(source, /<BrandLogo\s+showRoman/);
  assert.match(source, /className="landing-final-brand"/);
  assert.match(source, /<BrandLogo\s+className="landing-footer-logo"/);
  assert.match(source, /<Eyebrow>命 · 盘 · 读<\/Eyebrow>/);
  assert.doesNotMatch(source, /<Eyebrow>有时 · 命有其时<\/Eyebrow>/);
});

test('product shell topbar uses the shared brand logo', () => {
  const source = fs.readFileSync(new URL('../src/components/Shell.jsx', import.meta.url), 'utf8');

  assert.match(source, /import \{ BrandLogo \} from '\.\/brand\/BrandLogo\.jsx'/);
  assert.match(source, /<BrandLogo\s+size="small"\s+className="shell-brand-logo"/);
  assert.doesNotMatch(source, /\{matches\(meta\?\.rizhuGan/);
  assert.doesNotMatch(source, /\{.*meta\?\.rizhuGan[\s\S]*?· 命/);
});

test('browser chrome uses the Youshi brand instead of Vite defaults', () => {
  const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  const favicon = fs.readFileSync(new URL('../public/favicon.svg', import.meta.url), 'utf8');

  assert.match(html, /<title>有时<\/title>/);
  assert.match(html, /href="\/favicon\.svg\?v=youshi-/);
  assert.match(favicon, /M50 15V85/);
  assert.doesNotMatch(favicon, /863bff|Vite|vite/i);
});
