// frontend/tests/partner-birth-form.test.mjs
//
// PartnerBirthForm 是 React 组件 (.jsx)。本仓库的 node --test runner
// 不带 JSX/JSDOM 配置（见 birth-form.test.mjs / hepan-placement.test.mjs
// 等已有用例 —— 全部走源码字符串断言），所以这里也保持同样的约定：
// 用 fs.readFileSync 读源代码 + 正则验证关键逻辑接好。
//
// 行为校验本身由 partner-birth-validation.test.mjs 在
// buildPartnerBirthPayload 层完成；这里只负责保证 PartnerBirthForm
// 把校验结果与 onSubmit / 错误显示正确串起来。
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

import { buildPartnerBirthPayload, EMPTY_PARTNER_FORM } from '../src/components/hepan/partnerBirthValidation.js';

const SOURCE = fs.readFileSync(
  new URL('../src/components/hepan/PartnerBirthForm.jsx', import.meta.url),
  'utf8',
);

test('imports buildPartnerBirthPayload + EMPTY_PARTNER_FORM from validator', () => {
  assert.match(
    SOURCE,
    /import\s*\{\s*buildPartnerBirthPayload\s*,\s*EMPTY_PARTNER_FORM\s*\}\s*from\s*'\.\/partnerBirthValidation\.js'/,
  );
});

test('renders all six fields (date / time / hourUnknown / city / gender / nickname)', () => {
  assert.match(SOURCE, /type="date"/);
  assert.match(SOURCE, /type="time"/);
  assert.match(SOURCE, /type="checkbox"/);
  assert.match(SOURCE, /时辰未知/);
  assert.match(SOURCE, /aria-label="对方出生地"/);
  assert.match(SOURCE, /aria-label="对方性别"/);
  assert.match(SOURCE, /aria-label="对方昵称"/);
});

test('form uses noValidate (custom error UI, not browser default)', () => {
  assert.match(SOURCE, /<form[^>]*noValidate/);
});

test('happy-path submit calls onSubmit with parsed birth + nickname', () => {
  // wiring: handleSubmit 调用 buildPartnerBirthPayload(form)，再 onSubmit({ birth, nickname })
  assert.match(SOURCE, /buildPartnerBirthPayload\(form\)/);
  assert.match(
    SOURCE,
    /await\s+onSubmit\(\{\s*birth\s*,\s*nickname:\s*\(form\.nickname\s*\|\|\s*''\)\.trim\(\)\s*\|\|\s*null\s*\}\)/,
  );

  // sanity: 同一份 payload 在校验层确实能跑通 hourUnknown happy path
  const out = buildPartnerBirthPayload({
    ...EMPTY_PARTNER_FORM,
    date: '2000-05-07',
    hourUnknown: true,
  });
  assert.equal(out.year, 2000);
  assert.equal(out.month, 5);
  assert.equal(out.day, 7);
  assert.equal(out.hour, -1);
  assert.equal(out.minute, 0);
});

test('validator error is caught and rendered with role="alert"', () => {
  // try { build } catch { setError(message) }，并条件渲染 role="alert" 容器
  assert.match(
    SOURCE,
    /try\s*\{[\s\S]*?birth\s*=\s*buildPartnerBirthPayload\(form\)[\s\S]*?\}\s*catch\s*\(\s*e\s*\)\s*\{[\s\S]*?setError\(e\.message[\s\S]*?\)/,
  );
  assert.match(SOURCE, /role="alert"/);
  assert.match(SOURCE, /\{error\s*\?\s*<div[^>]*role="alert"/);

  // 空表单时校验层抛出包含 "出生日期" 的中文错误
  assert.throws(
    () => buildPartnerBirthPayload({ ...EMPTY_PARTNER_FORM }),
    /出生日期/,
  );
});

test('cancel button is conditional on onCancel prop', () => {
  assert.match(SOURCE, /onCancel\s*\?\s*\(/);
  assert.match(SOURCE, /onClick=\{onCancel\}/);
});

test('busy disables submit and swaps label to 提交中…', () => {
  assert.match(SOURCE, /disabled=\{busy\}/);
  assert.match(SOURCE, /busy\s*\?\s*'提交中…'\s*:\s*submitLabel/);
});

test('hourUnknown checkbox clears time when toggled on', () => {
  // setForm 里 time: e.target.checked ? '' : prev.time
  assert.match(SOURCE, /time:\s*e\.target\.checked\s*\?\s*''\s*:\s*prev\.time/);
});
