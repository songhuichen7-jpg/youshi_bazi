import test from 'node:test';
import assert from 'node:assert/strict';
import { replaceOklchInValue } from '../src/lib/saveImage.js';

// 用 stub 把每个 color token 替换成 "RGB[...]" 方便断言；真实运行时
// 这里会是 canvas getImageData 解析出来的 rgb(...) 串。
const stub = (raw) => `RGB[${raw}]`;


test('replaceOklchInValue: 不含 oklch / color-mix 的串原样返回', () => {
  assert.equal(replaceOklchInValue('rgb(0, 0, 0)', stub), 'rgb(0, 0, 0)');
  assert.equal(replaceOklchInValue('#fff', stub), '#fff');
  assert.equal(replaceOklchInValue('', stub), '');
});


test('replaceOklchInValue: 单个 oklch 整段替换', () => {
  assert.equal(
    replaceOklchInValue('oklch(0.7 0.18 60)', stub),
    'RGB[oklch(0.7 0.18 60)]',
  );
});


test('replaceOklchInValue: 带 alpha 的 oklch 也走得通', () => {
  assert.equal(
    replaceOklchInValue('oklch(0.2 0.05 60 / 0.3)', stub),
    'RGB[oklch(0.2 0.05 60 / 0.3)]',
  );
});


test('replaceOklchInValue: gradient 里多段 oklch 各自替换', () => {
  const result = replaceOklchInValue(
    'linear-gradient(135deg, oklch(0.7 0.18 60), oklch(0.4 0.2 90))',
    stub,
  );
  assert.equal(
    result,
    'linear-gradient(135deg, RGB[oklch(0.7 0.18 60)], RGB[oklch(0.4 0.2 90)])',
  );
});


test('replaceOklchInValue: color-mix(in oklch, ...) 作为整体替换，不破坏内部 oklch', () => {
  // color-mix 含嵌套 oklch — 不能把 inner oklch 单独替换掉再交给 canvas
  // 否则会变成 color-mix(in oklch, rgb(...) 60%, white)，canvas 不一定认
  // （也合法但更绕）。这里采取的策略是：碰到 color-mix(in oklch, ...) 整段
  // 交给 resolver，让 canvas 整体算成 rgb。
  const result = replaceOklchInValue(
    'color-mix(in oklch, oklch(0.7 0.18 60) 60%, white)',
    stub,
  );
  assert.equal(result, 'RGB[color-mix(in oklch, oklch(0.7 0.18 60) 60%, white)]');
});


test('replaceOklchInValue: color-mix(in srgb, ...) 等非 oklch 模式不处理（避免误伤）', () => {
  // 不是 oklch 颜色空间的 color-mix html2canvas 大概率支持；保留原样
  const result = replaceOklchInValue(
    'color-mix(in srgb, red 50%, blue)',
    stub,
  );
  assert.equal(result, 'color-mix(in srgb, red 50%, blue)');
});


test('replaceOklchInValue: box-shadow 多段含 oklch 与普通 rgb 混合', () => {
  const result = replaceOklchInValue(
    '0 4px 8px oklch(0.2 0.05 60 / 0.3), 0 0 0 1px rgb(200, 200, 200)',
    stub,
  );
  assert.equal(
    result,
    '0 4px 8px RGB[oklch(0.2 0.05 60 / 0.3)], 0 0 0 1px rgb(200, 200, 200)',
  );
});


test('replaceOklchInValue: 字面包含 "oklch" 但不是函数调用时不替换（防误伤）', () => {
  // 不太可能出现，但稳一点
  assert.equal(replaceOklchInValue('oklch-fallback', stub), 'oklch-fallback');
});
