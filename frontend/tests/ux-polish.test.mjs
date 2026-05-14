import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

import { buildChartVisibility } from '../src/lib/chartVisibility.js';
import { buildGenerationStatus, getWelcomeMessageState } from '../src/lib/chatStatus.js';
import { buildUserMenuProfile, reduceUserMenuOpen } from '../src/lib/userMenu.js';

test('buildChartVisibility hides engine fields that are absent and drops dangling separators', () => {
  const result = buildChartVisibility({
    meta: {
      rizhu: '甲戌',
      dayStrength: '',
      geju: '—',
      gejuNote: '',
      yongshen: '',
    },
    force: [],
    guards: [],
  });

  assert.deepEqual(result, {
    showDayStrengthDetails: false,
    showGeju: false,
    showYongshen: false,
    showForce: false,
    showGuards: false,
    dayMasterText: '甲戌',
    readingHeadline: '甲戌',
    readingSummary: '日主 甲戌',
  });
});

test('buildChartVisibility suppresses internal guard hints even when engine data exists', () => {
  const result = buildChartVisibility({
    meta: {
      rizhu: '甲戌',
      dayStrength: '身弱',
      geju: '食神格',
      yongshen: '木',
    },
    force: [{ name: '比肩', val: 4.4 }],
    guards: [{ type: 'liuhe', note: '子丑 六合 化 土' }],
  });

  assert.equal(result.showForce, true);
  assert.equal(result.showGuards, false);
});

test('buildGenerationStatus ignores removed verdict generation', () => {
  const result = buildGenerationStatus({
    verdicts: { status: 'streaming', body: '正在生成中' },
    dayunStreaming: true,
    liunianStreaming: true,
  });

  assert.deepEqual(result, {
    visible: false,
    text: '',
  });
});

test('buildGenerationStatus stays hidden for timing-page generation alone', () => {
  const result = buildGenerationStatus({
    dayunStreaming: true,
    liunianStreaming: true,
  });

  assert.deepEqual(result, {
    visible: false,
    text: '',
  });
});

test('getWelcomeMessageState does not mention removed comprehensive reading', () => {
  const result = getWelcomeMessageState({
    verdicts: { status: 'streaming' },
  });

  assert.equal(
    result.lead,
    '我已经看过你的命盘了。你可以：',
  );
  assert.equal(result.showDefaultGuidance, true);
});

test('FormScreen no longer starts comprehensive reading generation', () => {
  const source = fs.readFileSync(new URL('../src/components/FormScreen.jsx', import.meta.url), 'utf8');

  assert.doesNotMatch(source, /loadVerdicts/);
  assert.doesNotMatch(source, /streamVerdicts/);
  assert.doesNotMatch(source, /综合解读/);
});

test('reduceUserMenuOpen toggles open and closes on outside interactions', () => {
  assert.equal(reduceUserMenuOpen(false, { type: 'toggle' }), true);
  assert.equal(reduceUserMenuOpen(true, { type: 'toggle' }), false);
  assert.equal(reduceUserMenuOpen(true, { type: 'outside' }), false);
  assert.equal(reduceUserMenuOpen(true, { type: 'logout' }), false);
});

test('buildUserMenuProfile prefers nickname initial and masks known phone digits', () => {
  const result = buildUserMenuProfile({
    nickname: '测试用户',
    phone_last4: '1833',
    phone: '+8613800131833',
  });

  assert.deepEqual(result, {
    avatarUrl: null,
    avatarLabel: '测',
    displayName: '测试用户',
    isGuest: false,
    maskedPhone: '+86 138 *** 1833',
    plan: 'lite',
    planExpiresAt: null,
    role: 'user',
  });
});

test('share-card stage stretches to viewport height and centers the card', () => {
  const css = fs.readFileSync(new URL('../src/styles/card.css', import.meta.url), 'utf8');

  // .card-stage-mat fills remaining viewport via min-height calc, and the
  // base rule (top of file) keeps display: flex + center centering inside it
  assert.match(css, /\.card-stage-mat\s*\{[^}]*display:\s*flex[^}]*align-items:\s*center[^}]*justify-content:\s*center/s);
  assert.match(css, /min-height:\s*calc\(100vh\s*-\s*var\(--card-controls-height\)/s);
});

test('share-card + hepan-card play a flip-in animation on mount', () => {
  const css = fs.readFileSync(new URL('../src/styles/card.css', import.meta.url), 'utf8');
  const workspace = fs.readFileSync(
    new URL('../src/components/card/CardWorkspace.jsx', import.meta.url), 'utf8',
  );

  // keyframes exist + rotateY transform + opacity 0 → 1
  assert.match(css, /@keyframes share-card-flip-in/);
  assert.match(css, /rotateY\(-?9?2?deg\)/);
  // both card kinds animate
  assert.match(css, /\.card-document-stage \.share-card,\s*\.hepan-card\s*\{[^}]*animation:\s*share-card-flip-in/s);
  // prefers-reduced-motion fallback to fade
  assert.match(css, /prefers-reduced-motion: reduce[\s\S]*?share-card-fade-in/);
  // workspace bumps a tick on regenerate so React remounts the card and replays the animation
  assert.match(workspace, /generateTick/);
  assert.match(workspace, /setGenerateTick\(t => t \+ 1\)/);
  assert.match(workspace, /key=\{`\$\{activeCard\.share_slug/);
  assert.match(workspace, /\$\{generateTick\}`\}/);
});

test('hepan-bound chat focus pill renders both participants with avatars', () => {
  const chat = fs.readFileSync(new URL('../src/components/Chat.jsx', import.meta.url), 'utf8');
  const css = fs.readFileSync(new URL('../src/index.css', import.meta.url), 'utf8');

  // helper builds { a, b, label } from the hepan cache, bypassing the
  // explicit-label fallback in getConversationDisplayLabel
  assert.match(chat, /function buildHepanFocus/);
  assert.match(chat, /getHepanMineCached/);
  // pill JSX renders two AvatarBadges with the cache-derived names
  assert.match(chat, /chat-context-pill-pair/);
  assert.match(chat, /<AvatarBadge[^>]*hepanFocus\.a\.seed/s);
  assert.match(chat, /<AvatarBadge[^>]*hepanFocus\.b\.seed/s);
  // CSS hooks for the new pair layout
  assert.match(css, /\.chat-context-pill-pair\s*\{/);
  assert.match(css, /\.chat-context-pill-avatar\s*\{/);
});

test('hepan list rows center their actions vertically with the multi-line text', () => {
  const css = fs.readFileSync(new URL('../src/styles/hepan.css', import.meta.url), 'utf8');

  // .hepan-row used to use align-items: flex-start which left the actions
  // floating at the top of long rows; center keeps them on the visual midline
  assert.match(css, /\.hepan-row\s*\{[^}]*align-items:\s*center/s);
  assert.doesNotMatch(css, /\.hepan-row\s*\{[^}]*align-items:\s*flex-start/s);
});

test('LegalPage shows the BrandLogo as a brand mark + home link', () => {
  const src = fs.readFileSync(new URL('../src/components/LegalPage.jsx', import.meta.url), 'utf8');
  const css = fs.readFileSync(new URL('../src/index.css', import.meta.url), 'utf8');

  // imports BrandLogo and Link from react-router
  assert.match(src, /import\s+\{\s*BrandLogo\s*\}\s+from\s+['"][^'"]*BrandLogo/);
  assert.match(src, /from\s+['"]react-router-dom['"]/);
  // renders the brand mark wrapped in a Link to "/"
  assert.match(src, /<Link\s+to="\/"\s+className="legal-brand-link"/);
  assert.match(src, /<BrandLogo[^>]*className="legal-brand"/);
  // CSS hooks exist for the new brand link
  assert.match(css, /\.legal-brand-link\s*\{/);
  assert.match(css, /\.legal-brand\s+\.brand-logo-mark/);
});

test('left-topbar inner padding hugs the leftmost gutter so the brand logo is not offset', () => {
  const css = fs.readFileSync(new URL('../src/index.css', import.meta.url), 'utf8');

  // 12px on each side; the now-deleted 72px with-user-menu override is gone
  assert.match(css, /\.left-topbar-inner\s*\{[^}]*padding:\s*0 12px[^}]*\}/s);
  assert.doesNotMatch(css, /\.left-topbar-inner\.with-user-menu/);
});

test('avatar trigger stays chrome-free so only the circular avatar is visible', () => {
  const css = fs.readFileSync(new URL('../src/index.css', import.meta.url), 'utf8');

  assert.match(css, /\.user-menu-trigger\s*\{[^}]*border:\s*none;/s);
  assert.match(css, /\.user-menu-trigger\s*\{[^}]*background:\s*transparent;/s);
  assert.match(css, /\.user-menu-trigger\s*\{[^}]*box-shadow:\s*none;/s);
});

test('shell split width uses a css variable so mobile media queries can collapse the app', () => {
  const shell = fs.readFileSync(new URL('../src/components/Shell.jsx', import.meta.url), 'utf8');
  const css = fs.readFileSync(new URL('../src/index.css', import.meta.url), 'utf8');

  assert.doesNotMatch(shell, /gridTemplateColumns:\s*`1fr 6px/);
  assert.match(shell, /--right-pane-width/);
  assert.match(css, /grid-template-columns:\s*minmax\(0,\s*1fr\)\s+6px\s+var\(--right-pane-width,\s*720px\)/);
  assert.match(css, /@media \(max-width:\s*960px\)[\s\S]*\.shell-layout\s*\{[^}]*grid-template-columns:\s*1fr/);
  assert.match(css, /@media \(max-width:\s*960px\)[\s\S]*\.resize-handle\s*\{[^}]*display:\s*none/);
});

test('assistant rich text preserves markdown block structure', () => {
  const refChip = fs.readFileSync(new URL('../src/components/RefChip.jsx', import.meta.url), 'utf8');
  const css = fs.readFileSync(new URL('../src/index.css', import.meta.url), 'utf8');

  assert.match(refChip, /function renderRichTextBlocks/);
  assert.match(refChip, /<p className="rich-md-p"/);
  assert.match(refChip, /<ul className="rich-md-list"/);
  assert.match(refChip, /<ol className="rich-md-list"/);
  assert.match(refChip, /<blockquote className="rich-md-quote"/);
  assert.match(refChip, /<table className="rich-md-table"/);
  assert.match(refChip, /parseRef\(itemText/);
  assert.match(css, /\.rich-md\s*\{/);
  assert.match(css, /\.rich-md-list\s*\{/);
  assert.match(css, /\.rich-md-quote\s*\{/);
  assert.match(css, /\.rich-md-table-wrap\s*\{/);
  assert.match(css, /\.rich-md-table\s*\{/);
});

test('assistant replies stay visually plain instead of sitting inside a bordered card', () => {
  const css = fs.readFileSync(new URL('../src/index.css', import.meta.url), 'utf8');

  assert.match(css, /\.msg-ai-card\s*\{[^}]*padding:\s*0;/s);
  assert.match(css, /\.msg-ai-card\s*\{[^}]*border:\s*none;/s);
  assert.match(css, /\.msg-ai-card\s*\{[^}]*background:\s*transparent;/s);
  assert.match(css, /\.msg-ai-card\s*\{[^}]*box-shadow:\s*none;/s);
});

test('chat streaming buffers deltas and keeps unfinished markdown stable', () => {
  const chat = fs.readFileSync(new URL('../src/components/Chat.jsx', import.meta.url), 'utf8');
  const refChip = fs.readFileSync(new URL('../src/components/RefChip.jsx', import.meta.url), 'utf8');

  assert.match(chat, /createStreamingTextBuffer/);
  assert.match(chat, /scheduleAssistantDelta\(running\)/);
  assert.match(chat, /flushAssistantDelta\(\);[\s\S]*if \(full\) replaceLastAssistant\(full\)/);
  assert.match(chat, /streaming=\{isLast && chatStreaming\}/);
  assert.match(refChip, /splitRichTextBlocks\(text,\s*\{\s*streaming:/);
});

test('birth form labels are programmatically associated with their inputs', () => {
  const form = fs.readFileSync(new URL('../src/components/FormScreen.jsx', import.meta.url), 'utf8');

  assert.match(form, /<label className="form-label" htmlFor="birth-date">公历生日<\/label>/);
  assert.match(form, /<input id="birth-date" type="date"/);
  assert.match(form, /<label className="form-label" htmlFor="birth-time">出生时间<\/label>/);
  assert.match(form, /<input id="birth-time" type="time"/);
  assert.match(form, /<label className="form-label" htmlFor="birth-city">出生地<\/label>/);
  assert.match(form, /<input id="birth-city" type="text"/);
});

test('direct app visits hydrate auth and charts before redirecting landing state away', () => {
  const appShell = fs.readFileSync(new URL('../src/components/AppShell.jsx', import.meta.url), 'utf8');

  assert.match(appShell, /const \[bootstrapped,\s*setBootstrapped\]/);
  assert.match(appShell, /await bootstrapAuthGate\(\{ store: useAppStore, me, guestLogin \}\)/);
  assert.match(appShell, /await useAppStore\.getState\(\)\.enterFromLanding\(\)/);
  assert.match(appShell, /if \(!bootstrapped\) return/);
});

test('primary shell navigation and icon-only controls expose button semantics', () => {
  const shell = fs.readFileSync(new URL('../src/components/Shell.jsx', import.meta.url), 'utf8');
  const chartSwitcher = fs.readFileSync(new URL('../src/components/ChartSwitcher.jsx', import.meta.url), 'utf8');
  const conversationSwitcher = fs.readFileSync(new URL('../src/components/ConversationSwitcher.jsx', import.meta.url), 'utf8');
  const form = fs.readFileSync(new URL('../src/components/FormScreen.jsx', import.meta.url), 'utf8');

  assert.match(shell, /<button[\s\S]*aria-pressed=\{view === 'chart'\}[\s\S]*>命 盘<\/button>/);
  assert.match(shell, /aria-label=\{resetPending \? '再点一次清空所有命盘和聊天记录' : '清空所有命盘和聊天记录'\}/);
  assert.match(chartSwitcher, /aria-label="重命名命盘"/);
  assert.match(chartSwitcher, /aria-label="删除命盘"/);
  assert.match(conversationSwitcher, /aria-label="重命名对话"/);
  assert.match(conversationSwitcher, /aria-label="删除对话"/);
  assert.match(form, /<button[\s\S]*className="back-link"[\s\S]*>← 返回<\/button>/);
});

test('ClassicsPanel renders persona + verdict layout with new subtitle', () => {
  const src = fs.readFileSync(
    new URL('../src/components/ClassicsPanel.jsx', import.meta.url), 'utf8',
  );
  // 新副标题
  assert.match(src, /古人是这样形容这种命的/);
  // 模块标题
  assert.match(src, /古 书 定 调/);
  // 新视图建造器
  assert.match(src, /buildPersonaDisplay/);
  assert.match(src, /buildVerdictDisplay/);
  // 双区块 className
  assert.match(src, /persona-card/);
  assert.match(src, /verdict-strip/);
  // —— 校验前端不再渲染旧 items list ——
  assert.doesNotMatch(src, /classics-list/);
  assert.doesNotMatch(src, /classics-toggle/);
  // 空态
  assert.match(src, /此盘古籍未见直接命例/);
});

test('persona + verdict CSS classes are defined', () => {
  const css = fs.readFileSync(new URL('../src/index.css', import.meta.url), 'utf8');
  assert.match(css, /\.persona-card\s*\{/);
  assert.match(css, /\.persona-quote\s*\{/);
  assert.match(css, /\.persona-plain\s*\{/);
  assert.match(css, /\.persona-fit-note\s*\{/);
  assert.match(css, /\.verdict-strip\s*\{/);
  assert.match(css, /\.verdict-divider\s*\{/);
  assert.match(css, /\.verdict-quote\s*\{/);
});
