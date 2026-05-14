import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

test('FormScreen requires terms and privacy agreement before chart generation', () => {
  const source = fs.readFileSync(new URL('../src/components/FormScreen.jsx', import.meta.url), 'utf8');
  const css = fs.readFileSync(new URL('../src/index.css', import.meta.url), 'utf8');

  assert.match(source, /const \[privacyAgreed,\s*setPrivacyAgreed\]\s*=\s*useState\(false\)/);
  assert.match(source, /if \(!privacyAgreed\) return rejectForm\('请先阅读并同意用户协议和隐私政策', 'privacy_agreement'\)/);
  assert.match(source, /className="form-privacy-agreement"/);
  assert.match(source, /to="\/legal\/terms"[\s\S]*《服务条款》/);
  assert.match(source, /to="\/legal\/privacy"[\s\S]*《隐私政策》/);
  assert.match(source, /disabled=\{!privacyAgreed\}/);
  assert.match(source, /className="form-actions"/);

  assert.match(css, /\.form-privacy-agreement[\s\S]*border-top:\s*1px solid var\(--line\)/);
  assert.match(css, /\.form-privacy-agreement-copy a:focus-visible/);
  assert.match(css, /\.form-wrap\s*\{[^}]*padding:\s*40px 24px 32px/);
  assert.match(css, /\.form-row\s*\{[^}]*margin-bottom:\s*24px/);
  assert.match(css, /\.form-privacy-agreement\s*\{[^}]*margin-top:\s*22px/);
  assert.match(css, /\.form-actions\s*\{[^}]*margin-top:\s*28px/);
});

test('LandingHome moves privacy introduction behind product and trust sections', () => {
  const source = fs.readFileSync(new URL('../src/components/landing/LandingHome.jsx', import.meta.url), 'utf8');

  const personaIndex = source.indexOf('二十种命盘人格');
  const trustIndex = source.indexOf('<Eyebrow>凭 据</Eyebrow>');
  const privacyIndex = source.indexOf('<Eyebrow>数 · 据 · 安 · 全</Eyebrow>');
  const finalIndex = source.indexOf('<Eyebrow>有 · 时</Eyebrow>');

  assert.ok(personaIndex >= 0, 'expected persona intro section');
  assert.ok(trustIndex >= 0, 'expected trust section');
  assert.ok(privacyIndex >= 0, 'expected privacy section');
  assert.ok(finalIndex >= 0, 'expected final CTA section');
  assert.ok(personaIndex < privacyIndex, 'privacy should no longer be the first intro section');
  assert.ok(trustIndex < privacyIndex, 'privacy should appear after the trust section');
  assert.ok(privacyIndex < finalIndex, 'privacy should remain before the final CTA');
  assert.match(source, /<section id="intro" className="landing-section">[\s\S]*二十种命盘人格/);
});
