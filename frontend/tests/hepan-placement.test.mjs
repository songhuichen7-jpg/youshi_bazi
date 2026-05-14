import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

test('app routes register /hepan/:slug', () => {
  const source = fs.readFileSync(new URL('../src/App.jsx', import.meta.url), 'utf8');
  assert.match(source, /path="\/hepan\/:slug"/);
  assert.match(source, /HepanScreen/);
  assert.match(source, /\/hepan\/:slug/);
});

// Spec 03 §三 + 04b §四: hepan card front structure
test('hepan card surfaces label, subtags, dual roles, modifier, cta', () => {
  const source = fs.readFileSync(new URL('../src/components/hepan/HepanCard.jsx', import.meta.url), 'utf8');

  assert.match(source, /hepan-card-color-field/);
  assert.match(source, /hepan-card-head/);
  assert.match(source, /hepan-card-art-stage/);
  assert.match(source, /hepan-state-pair/);          // readable state rhythm label
  assert.match(source, /hepan-card-illustration/);   // A/B 单人卡融合插画
  assert.match(source, /hepan-pair-art/);
  assert.match(source, /hepan-relation-art/);
  assert.match(source, /hepan-card-copy-panel/);
  assert.match(source, /hepan-card-label/);          // 关系标签 (大字)
  assert.match(source, /hepan-card-label-wrap/);
  assert.match(source, /hepan-card-subtags/);        // 3 chip
  assert.match(source, /hepan-roles/);               // A/B 角色对照
  assert.match(source, /hepan-description/);
  assert.match(source, /hepan-modifier/);            // 04b 动态修饰
  assert.match(source, /hepan-cta/);
  assert.match(source, /hepan-card-foot/);
});

// Spec 质检 #4: hepan card front carries no raw bazi terminology
test('hepan card front carries no raw bazi terminology', () => {
  const source = fs.readFileSync(new URL('../src/components/hepan/HepanCard.jsx', import.meta.url), 'utf8');
  // Field references — only allow the high-level relationship/role fields
  assert.doesNotMatch(source, /hepan\.day_stem/);
  assert.doesNotMatch(source, /hepan\.ge_ju/);
  assert.doesNotMatch(source, /\.day_stem/);
  // Visible Chinese terms
  assert.doesNotMatch(source, /[>\s]日主[<\s]/);
  assert.doesNotMatch(source, /[>\s]格局[<\s]/);
});

test('hepan card uses 3:4 portrait aspect ratio', () => {
  const css = fs.readFileSync(new URL('../src/styles/hepan.css', import.meta.url), 'utf8');
  assert.match(css, /\.hepan-card[\s\S]*aspect-ratio:\s*3\s*\/\s*4/);
  // Pair theme color drives accent
  assert.match(css, /--card-accent:\s*var\(--theme/);
});

test('hepan card protects long relationship tags from clipping', () => {
  const css = fs.readFileSync(new URL('../src/styles/hepan.css', import.meta.url), 'utf8');
  assert.match(css, /\.hepan-card-subtags[\s\S]*display:\s*grid/);
  assert.match(css, /\.hepan-card-subtags li[\s\S]*overflow-wrap:\s*anywhere/);
  assert.match(css, /\.hepan-role-text[\s\S]*overflow-wrap:\s*anywhere/);
  assert.match(css, /\.hepan-copy-stack[\s\S]*min-height:\s*0/);
});

test('hepan nickname row truncates user-provided long names without growing the card', () => {
  const css = fs.readFileSync(new URL('../src/styles/hepan.css', import.meta.url), 'utf8');
  const nicksRule = css.match(/\.hepan-nicks\s*\{[\s\S]*?\n\}/)?.[0] || '';
  const nickRule = css.match(/\.hepan-nick\s*\{[\s\S]*?\n\}/)?.[0] || '';

  assert.match(nicksRule, /flex-wrap:\s*nowrap/);
  assert.match(nicksRule, /min-width:\s*0/);
  assert.match(nickRule, /max-width:\s*42%/);
  assert.match(nickRule, /text-overflow:\s*ellipsis/);
  assert.match(nickRule, /white-space:\s*nowrap/);
});

test('hepan card clamps variable copy while keeping footer in normal flow', () => {
  const css = fs.readFileSync(new URL('../src/styles/hepan.css', import.meta.url), 'utf8');
  const roleRule = css.match(/\.hepan-role-text\s*\{[\s\S]*?\n\}/)?.[0] || '';
  const descRule = css.match(/\.hepan-description\s*\{[\s\S]*?\n\}/)?.[0] || '';
  const modifierRule = css.match(/\.hepan-modifier\s*\{[\s\S]*?\n\}/)?.[0] || '';
  const ctaRule = css.match(/\.hepan-cta\s*\{[\s\S]*?\n\}/)?.[0] || '';
  const footRule = css.match(/\.hepan-card-foot\s*\{[\s\S]*?\n\}/)?.[0] || '';

  assert.match(roleRule, /-webkit-line-clamp:\s*2/);
  assert.match(descRule, /-webkit-line-clamp:\s*2/);
  assert.match(modifierRule, /-webkit-line-clamp:\s*2/);
  assert.match(ctaRule, /-webkit-line-clamp:\s*2/);
  assert.match(footRule, /grid-row:\s*4/);
  assert.match(footRule, /position:\s*relative/);
  assert.match(footRule, /bottom:\s*auto/);
  assert.match(footRule, /z-index:\s*3/);
  assert.doesNotMatch(footRule, /position:\s*absolute/);
});

test('hepan card follows the same poster-grid system as the single card with a footer row', () => {
  const source = fs.readFileSync(new URL('../src/components/hepan/HepanCard.jsx', import.meta.url), 'utf8');
  const css = fs.readFileSync(new URL('../src/styles/hepan.css', import.meta.url), 'utf8');
  const cardRule = css.match(/\.hepan-card\s*\{[\s\S]*?\n\}/)?.[0] || '';
  const copyRule = css.match(/\.hepan-card-copy-panel\s*\{[\s\S]*?\n\}/)?.[0] || '';
  const footRule = css.match(/\.hepan-card-foot\s*\{[\s\S]*?\n\}/)?.[0] || '';
  const chipRule = css.match(/\.hepan-card-subtags li\s*\{[\s\S]*?\n\}/)?.[0] || '';

  assert.match(source, /aria-hidden="true" className="hepan-card-color-field"/);
  assert.doesNotMatch(source, /hepan-card-frame/);
  assert.doesNotMatch(css, /\.hepan-card-art-stage::after/);
  assert.doesNotMatch(css, /\.hepan-card-color-field::after/);
  assert.match(cardRule, /--card-paper:\s*#fff;/);
  assert.match(cardRule, /--hepan-art-row:\s*(?:14\d|15\d|16\d)px/);
  assert.match(cardRule, /--hepan-copy-min-row:\s*(?:29\d|30\d|31\d|32\d)px/);
  assert.match(cardRule, /--hepan-foot-row:/);
  assert.match(cardRule, /background:\s*#fff/);
  assert.match(cardRule, /display:\s*grid/);
  assert.match(cardRule, /grid-template-rows:\s*var\(--hepan-head-row\)\s+var\(--hepan-art-row\)\s+minmax\(var\(--hepan-copy-min-row\),\s*1fr\)\s+var\(--hepan-foot-row\)/);
  assert.match(css, /\.hepan-card > :not\(\.hepan-card-color-field\)/);
  assert.match(copyRule, /min-height:\s*0/);
  assert.match(copyRule, /overflow:\s*hidden/);
  assert.match(copyRule, /padding-bottom:\s*8px/);
  assert.match(footRule, /grid-row:\s*4/);
  assert.match(footRule, /position:\s*relative/);
  assert.match(footRule, /bottom:\s*auto/);
  assert.match(footRule, /z-index:\s*3/);
  assert.doesNotMatch(footRule, /position:\s*absolute/);
  assert.match(css, /\.hepan-card-illustration[\s\S]*aspect-ratio:\s*1\.2\s*\/\s*1/);
  assert.match(css, /\.hepan-relation-art/);
  assert.match(css, /\.hepan-pair-side-a/);
  assert.match(css, /\.hepan-pair-side-b/);
  assert.match(css, /\.hepan-pair-orbit/);
  assert.match(chipRule, /background:[\s\S]*color-mix/);
  assert.match(chipRule, /overflow-wrap:\s*anywhere/);
  assert.match(source, /relationIllustrationSrc\(hepan\.category\)/);
  assert.match(source, /a\.illustration_url/);
  assert.match(source, /b\.illustration_url/);
  assert.doesNotMatch(source, /\{hepan\.state_pair\}/);
});

test('hepan invite landing page guides B with inviter context', () => {
  const source = fs.readFileSync(new URL('../src/components/hepan/HepanScreen.jsx', import.meta.url), 'utf8');
  assert.match(source, /邀请你来合盘/);
  assert.match(source, /hepan-invite/);
  assert.match(source, /提交我的生日/);
  assert.match(source, /加密保存到邀请方的合盘记录/);
});

test('completed hepan card can be exported as an image', () => {
  const source = fs.readFileSync(new URL('../src/components/hepan/HepanScreen.jsx', import.meta.url), 'utf8');
  assert.match(source, /saveCardAsImage/);
  assert.match(source, /hepan-save-button/);
  assert.match(source, /导出合盘图/);
  assert.match(source, /hepan_card_save/);
});

test('topbar no longer exposes a separate hepan entry', () => {
  const shell = fs.readFileSync(new URL('../src/components/Shell.jsx', import.meta.url), 'utf8');

  assert.doesNotMatch(shell, /HepanInviteButton/);
  assert.doesNotMatch(shell, /打开合盘邀请/);
});

test('CardWorkspace keeps copy-link invite as a fallback hepan path', () => {
  const source = fs.readFileSync(new URL('../src/components/card/CardWorkspace.jsx', import.meta.url), 'utf8');
  assert.match(source, /postHepanInvite/);
  assert.match(source, /\/hepan\//);
  assert.match(source, /handleCopyPairInvite/);
  // Task 23: 复制不再贴 bare URL，走 composeHepanShareText 包装话术；
  // toast 改成 "已复制 — 把链接发给对方，TA 填完生日就合上了"。
  assert.match(source, /composeHepanShareText/);
  assert.match(source, /已复制 — 把链接发给对方/);
  // ?from=invite 后缀不再附加 — 在新 flow 里它没有意义
  assert.doesNotMatch(source, /\?from=invite/);
  // 不知道对方生日 → 走"发邀请让 TA 自己填"作为回退入口
  assert.match(source, /发邀请让 TA 自己填/);
});

test('HepanScreen pending state always renders B view (Task 23 rollback)', () => {
  const source = fs.readFileSync(new URL('../src/components/hepan/HepanScreen.jsx', import.meta.url), 'utf8');
  // B 视角的关键文案保留
  assert.match(source, /邀请你来合盘/);
  assert.match(source, /提交我的生日/);
  // 不再有 isCreatorPending 分支或 A 视角的 share / copy / direct-fill 块
  assert.doesNotMatch(source, /isCreatorPending/);
  assert.doesNotMatch(source, /已发起合盘邀请/);
  assert.doesNotMatch(source, /复制邀请链接/);
  assert.doesNotMatch(source, /已经知道对方生日/);
  assert.doesNotMatch(source, /hepan-invite-share/);
  assert.doesNotMatch(source, /hepan-invite-copy/);
  assert.doesNotMatch(source, /hepan-invite-direct-fill/);
  assert.doesNotMatch(source, /hepan-invite-avatar-inline/);
  assert.doesNotMatch(source, /copyInviteLink/);
  assert.doesNotMatch(source, /fullInviteUrl/);
});

test('CardWorkspace hepan tab is a list-driven management panel', () => {
  const source = fs.readFileSync(new URL('../src/components/card/CardWorkspace.jsx', import.meta.url), 'utf8');

  // 仍然走 postHepanComplete + PartnerBirthForm 的 onSubmit 通路
  assert.match(source, /postHepanComplete/);
  assert.match(source, /PartnerBirthForm/);
  assert.match(source, /HepanList/);
  assert.match(source, /handlePartnerSubmit/);
  assert.match(source, /handleAskFromList/);
  assert.match(source, /handleCopyFromList/);
  assert.match(source, /cardMode/);
  assert.match(source, /单人卡/);
  assert.match(source, /合盘卡/);
  assert.match(source, /生成合盘卡片/);
  assert.match(source, /\+ 新建合盘/);
  // 列表点 [追问] 通过 ensureHepanConversation 打开对话
  assert.match(source, /ensureHepanConversation/);
  assert.doesNotMatch(source, /卡片工作台/);
  // 旧 form / 旧状态字段都已经移除
  assert.doesNotMatch(source, /card-hepan-compact-form/);
  assert.doesNotMatch(source, /card-birth-form/);
  assert.doesNotMatch(source, /handleCompletePair/);
  assert.doesNotMatch(source, /activePairResult/);
  assert.doesNotMatch(source, /pairResultChartId/);
  assert.doesNotMatch(source, /EMPTY_PARTNER_FORM/);
  assert.doesNotMatch(source, /hepan_label/);
});

test('hepan art keeps old relation assets versioned for compatibility', () => {
  const art = fs.readFileSync(new URL('../src/lib/hepanArt.js', import.meta.url), 'utf8');
  assert.match(art, /天作搭子/);
  assert.match(art, /镜像搭子/);
  assert.match(art, /同频搭子/);
  assert.match(art, /滋养搭子/);
  assert.match(art, /火花搭子/);
  assert.match(art, /互补搭子/);
  assert.match(art, /\/static\/hepan\/illustrations/);
  assert.match(art, /HEPAN_ART_VERSION/);
});
