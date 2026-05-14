import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const SRC = readFileSync(
  new URL('../src/components/OnboardingModal.jsx', import.meta.url),
  'utf8',
);

test('imports AvatarBadge for the avatar preview', () => {
  assert.match(SRC, /from\s+['"][^'"]*AvatarBadge/);
});

test('imports rerollNickname + updateProfile + uploadAvatar', () => {
  assert.match(SRC, /rerollNickname/);
  assert.match(SRC, /updateProfile/);
  assert.match(SRC, /uploadAvatar/);
});

test('shows kicker + H1 + sub from spec', () => {
  assert.match(SRC, /取一个名字\s*给自己/);
  assert.match(SRC, /欢迎.*命盘世界|有时.*命盘/);
});

test('renders 2 main buttons: 完成 + 稍后再说', () => {
  assert.match(SRC, /完成/);
  assert.match(SRC, /稍后再说/);
});

test('shows "之后随时在左下角个人中心修改" hint', () => {
  assert.match(SRC, /左下角个人中心/);
});

test('reroll button calls rerollNickname', () => {
  assert.match(SRC, /换一个|↻/);
});

test('both 完成 and 稍后再说 paths PATCH mark_onboarded=true', () => {
  assert.match(SRC, /mark_onboarded\s*:\s*true/);
});

test('uploads via input type="file" + drag/drop', () => {
  assert.match(SRC, /type="file"|onChange=\{.*file/);
});
