import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

// 退出登录后, 用户必须落回访客首页 (/), 不能停在 /app 让 AppShell 渲染
// 内部那个旧 'landing' screen.

test('UserMenu logout calls navigate("/") after store.logout()', () => {
  const source = fs.readFileSync(new URL('../src/components/UserMenu.jsx', import.meta.url), 'utf8');

  // 必须 import useNavigate
  assert.match(source, /import.*useNavigate.*from\s+['"]react-router-dom['"]/);
  // 调用 navigate('/', ...) 把用户推回访客首页
  assert.match(source, /navigate\(['"]\/['"]/);
  // logout button 的 onClick 现在是 async, 等 store.logout 完才 navigate
  assert.match(source, /async\s*\(\)\s*=>\s*\{[\s\S]*?await\s+logout\(\)[\s\S]*?navigate/);
});

test('AppShell no longer renders the legacy LandingScreen for screen="landing"', () => {
  const source = fs.readFileSync(new URL('../src/components/AppShell.jsx', import.meta.url), 'utf8');

  // 不应再 import LandingScreen
  assert.doesNotMatch(source, /import\s+FormScreen,\s*\{\s*LandingScreen/);
  // 不应再有 content = <LandingScreen />
  assert.doesNotMatch(source, /content\s*=\s*<LandingScreen/);
  // 应该有 useEffect 兜底跳 / 当 screen 落到 'landing'
  assert.match(source, /useNavigate/);
  assert.match(source, /screen\s*===\s*['"]landing['"][\s\S]*?navigate\(['"]\/['"]/);
});

test('store.logout still resets to clean initial state (defense in depth)', () => {
  const source = fs.readFileSync(new URL('../src/store/useAppStore.js', import.meta.url), 'utf8');

  // logout 仍然清掉 user / charts / session — 这是 store 的本职
  assert.match(source, /logout:\s*async/);
  assert.match(source, /clearAuthSessionHint\(\)/);
  assert.match(source, /clearSession\(\)/);
});
