import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

test('LandingHome covers the editorial single-page narrative', () => {
  const source = fs.readFileSync(new URL('../src/components/landing/LandingHome.jsx', import.meta.url), 'utf8');

  // Hero — 品牌标识点题 + 主标题保留 + 用户提供的时序诗
  assert.match(source, /landing-hero/);
  assert.match(source, /BrandLogo\s+showRoman/);
  assert.match(source, /<Eyebrow>命 · 盘 · 读<\/Eyebrow>/);
  assert.match(source, /一个/);
  assert.match(source, /命理工具/);
  assert.match(source, /万事都有它出现的时刻/);
  assert.match(source, /人也在自己的时序里慢慢展开/);
  // 二十种人格
  assert.match(source, /二十种命盘人格/);
  assert.match(source, /给你的命盘/);
  // 关系
  assert.match(source, /你和 TA 的关系/);
  assert.match(source, /不是合不合/);
  assert.match(source, /RELATION_CATEGORIES/);
  assert.match(source, /五大类、二一〇种关系变体/);
  assert.doesNotMatch(source, /六大类/);
  // 好玩问法
  assert.match(source, /PLAY_CARDS/);
  assert.match(source, /电影、音乐和花/);
  assert.match(source, /MediaCard/);
  // 起卦作为介绍流里的独立说明，不混在小展品卡片里。
  assert.match(source, /landing-gua-section/);
  assert.match(source, /一件具体的事/);
  assert.match(source, /什么问题适合起卦/);
  assert.match(source, /GuaCard/);
  assert.ok(
    source.indexOf('landing-play-section') < source.indexOf('landing-gua-section'),
    'expected gua introduction to appear after the movie/music/play-card section',
  );
  assert.ok(
    source.indexOf('landing-gua-section') < source.indexOf('你和 TA 的关系'),
    'expected gua introduction to appear before the relationship section',
  );
  // 凭据
  assert.match(source, /凭 据/);
  assert.match(source, /古籍真本/);
  assert.match(source, /TRUST_METRICS/);
  // 时序收尾 — 纯诗意收束, 加品牌定位句
  assert.match(source, /landing-final/);
  assert.match(source, /和自己的时间/);
  assert.match(source, /坐下来谈一谈/);
});

test('LandingHome 主 CTA 在 Hero, Final 段只有低声 CTA (不与 Hero 同款)', () => {
  const source = fs.readFileSync(new URL('../src/components/landing/LandingHome.jsx', import.meta.url), 'utf8');
  const handlers = source.match(/onClick=\{handleStart\}/g) || [];
  // 两处入口：Hero 主 CTA + Final 收束段的低声 CTA。
  assert.equal(handlers.length, 2, `expected 2 CTA handlers (hero + final), got ${handlers.length}`);

  // Hero 用 landing-cta-primary（黑底白字），Final 用 landing-cta-quiet（轮廓款）
  const finalSection = source.match(/landing-final[\s\S]*?<\/section>/);
  assert.ok(finalSection, 'expected to find landing-final section');
  assert.doesNotMatch(finalSection[0], /landing-cta-primary/);
  assert.match(finalSection[0], /landing-cta-quiet/);
});

test('LandingHome footer exposes trust and support links quietly', () => {
  const source = fs.readFileSync(new URL('../src/components/landing/LandingHome.jsx', import.meta.url), 'utf8');
  const css = fs.readFileSync(new URL('../src/styles/landing.css', import.meta.url), 'utf8');
  const finalSection = source.match(/landing-final[\s\S]*?<\/section>/);

  assert.ok(finalSection, 'expected to find landing-final section');
  assert.match(finalSection[0], /landing-final-footer/);
  assert.match(finalSection[0], /\/legal\/about/);
  assert.match(finalSection[0], /\/legal\/privacy/);
  assert.match(finalSection[0], /\/legal\/terms/);
  assert.match(finalSection[0], /mailto:songhuichen7@gmail\.com\?subject=有时%20·%20反馈/);
  assert.match(finalSection[0], /关于/);
  assert.match(finalSection[0], /隐私政策/);
  assert.match(finalSection[0], /服务条款/);
  assert.match(finalSection[0], /反馈/);
  assert.match(css, /\.landing-final-links/);
  assert.match(css, /\.landing-final-links a[\s\S]*min-height:\s*44px/);
});

test('LandingHome shows user-facing breadth metrics (no dev-internal numbers)', () => {
  const source = fs.readFileSync(new URL('../src/components/landing/LandingHome.jsx', import.meta.url), 'utf8');
  // Trust metrics 全部讲产品丰富度, 不讲开发内部数字 (632 测试这种)
  assert.match(source, /20.*?基础人格/);
  assert.match(source, /200.*?人格细标签/);
  assert.match(source, /5.*?古籍真本/);
  assert.match(source, /210.*?关系组合/);
  assert.doesNotMatch(source, /632/);
  assert.doesNotMatch(source, /单元测试/);
  // 老 gallery 用 SHOWCASE_TYPES，新轮播用 PERSONA_POOL；任一存在都算合格
  assert.match(source, /SHOWCASE_TYPES|PERSONA_POOL/);
});

test('LandingHome 不暴露内部方法论给用户 ("正面重构"/"LLM"/"反幻觉")', () => {
  const source = fs.readFileSync(new URL('../src/components/landing/LandingHome.jsx', import.meta.url), 'utf8');
  // 关系段不应有"正面重构"或"碰撞型搭子"这种暴露包装意图的话
  assert.doesNotMatch(source, /正面重构/);
  assert.doesNotMatch(source, /碰撞型搭子/);
  // 凭据段不应有 LLM / 反幻觉 这种技术词
  assert.doesNotMatch(source, /LLM/);
  assert.doesNotMatch(source, /反幻觉/);
  assert.doesNotMatch(source, /占卜机/);
});

test('LandingHome introduces movie, music, and flower cards as aesthetic product previews', () => {
  const source = fs.readFileSync(new URL('../src/components/landing/LandingHome.jsx', import.meta.url), 'utf8');
  const css = fs.readFileSync(new URL('../src/styles/landing.css', import.meta.url), 'utf8');

  assert.match(source, /用一部电影形容我这盘/);
  assert.match(source, /豆瓣搜索/);
  assert.match(source, /用一首歌形容我的关系模式/);
  assert.match(source, /网易云搜索/);
  assert.match(source, /用一种花形容我这盘/);
  assert.match(source, /雨后玉兰/);
  assert.match(source, /清白、慢开，有一点冷香/);
  // 上线前砍掉的三种卡片：天气/气味/书 — 素材风格不统一、价值密度低。
  assert.doesNotMatch(source, /用一种天气形容/);
  assert.doesNotMatch(source, /用一种气味形容/);
  assert.doesNotMatch(source, /推荐一本书让我读懂自己/);
  assert.doesNotMatch(source, /kind:\s*'gua'/);
  const playCardsBlock = source.match(/const PLAY_CARDS = \[[\s\S]*?\];/);
  assert.ok(playCardsBlock, 'expected to find PLAY_CARDS block');
  assert.doesNotMatch(playCardsBlock[0], /这件事现在要不要推进/);
  assert.match(source, /landing-play-card/);
  assert.match(source, /MediaCard/);
  assert.doesNotMatch(source, /真实卡片样子/);
  assert.doesNotMatch(source, /landing-real-card-stage/);

  assert.match(css, /\.landing-play-grid[\s\S]*grid-template-columns:\s*repeat\(/);
  assert.match(css, /\.landing-gua-section/);
  assert.match(css, /\.landing-gua-grid[\s\S]*grid-template-columns/);
  assert.match(css, /\.landing-gua-card/);
  assert.match(css, /\.landing-play-object[\s\S]*min-height:\s*136px/);
  assert.match(css, /\.landing-play-object[\s\S]*align-items:\s*flex-start/);
  assert.match(css, /\.landing-play-card \.media-card[\s\S]*grid-template-columns:\s*58px minmax\(0,\s*1fr\) auto/);
  assert.match(css, /\.landing-play-card \.media-card-thumb[\s\S]*width:\s*48px/);
  assert.match(css, /\.landing-visual-artifact[\s\S]*grid-template-columns:\s*104px minmax\(0,\s*1fr\)/);
  assert.doesNotMatch(css, /\.landing-play-gua/);
  assert.match(css, /@media[^{]+max-width:\s*560px[\s\S]*\.landing-play-card \.media-card[\s\S]*grid-template-columns:\s*48px minmax\(0,\s*1fr\)/);
});

test('LandingHome uses serif typography for display titles (Songti / Source Han Serif)', () => {
  const css = fs.readFileSync(new URL('../src/styles/landing.css', import.meta.url), 'utf8');
  // 衬线字体栈用于标题
  assert.match(css, /landing-display-title[\s\S]*?font-family:[\s\S]*?Songti SC|Source Han Serif/);
  assert.match(css, /landing-section-title/);
  assert.match(css, /landing-final-title/);
});

test('LandingHome uses paper-white palette (no warm radial backdrop, near-white base)', () => {
  const css = fs.readFileSync(new URL('../src/styles/landing.css', import.meta.url), 'utf8');
  // landing-paper 接近纯白
  assert.match(css, /--landing-paper:\s*#fcfcfa/);
  // 黑色 CTA
  assert.match(css, /\.landing-cta-primary[\s\S]*?background:\s*#1a1a1a/);
  // 旧的 hero 暖色径向渐变 backdrop 应当消失
  assert.doesNotMatch(css, /\.landing-hero[\s\S]*?radial-gradient.+rgba\(82,\s*183/);
});

test('Hero title — single line, "理性" muted accent, contained size', () => {
  const source = fs.readFileSync(new URL('../src/components/landing/LandingHome.jsx', import.meta.url), 'utf8');
  const css = fs.readFileSync(new URL('../src/styles/landing.css', import.meta.url), 'utf8');

  // JSX: 一个 + <span class="landing-title-muted">理性</span> + 的命理工具, 不换行
  assert.match(source, /landing-title-muted/);
  assert.match(source, /一个<span className="landing-title-muted">理性<\/span>的命理工具/);
  const heroTitleMatch = source.match(/<h1[\s\S]*?landing-display-title[\s\S]*?<\/h1>/);
  assert.ok(heroTitleMatch, 'expected to find landing-display-title h1');
  assert.doesNotMatch(heroTitleMatch[0], /<br/);

  // CSS: muted 灰 + 单行 nowrap + 字号 60 (克制版)
  assert.match(css, /\.landing-title-muted[\s\S]*?color:\s*#c0bdb4/);
  assert.match(css, /\.landing-display-title[\s\S]*?font-size:\s*60px/);
  assert.match(css, /\.landing-display-title[\s\S]*?white-space:\s*nowrap/);
});

test('CTA enters AppShell immediately and lets bootstrap hydrate state', () => {
  const source = fs.readFileSync(new URL('../src/components/landing/LandingHome.jsx', import.meta.url), 'utf8');

  // 不再是 <Link to="/app">; 改成 button + onClick 先进 AppShell。
  // AppShell 负责恢复登录态和命盘，避免 CTA 卡在 landing 页等接口。
  assert.match(source, /useNavigate/);
  assert.match(source, /handleStart/);
  assert.match(source, /navigate\('\/app'\)/);
  // <button ... onClick={handleStart}>
  assert.match(source, /onClick=\{handleStart\}/);
  assert.doesNotMatch(source, /await enterFromLanding\(\)/);
  // 确保不再用 Link 直跳 (这会跳过 store action 导致 AppShell screen='landing')
  assert.doesNotMatch(source, /<Link\s+to="\/app"\s+className="landing-cta-primary"/);
});

test('Hero mockup renders the 命盘档案 + 对话 dual panels', () => {
  const source = fs.readFileSync(new URL('../src/components/landing/LandingHome.jsx', import.meta.url), 'utf8');
  assert.match(source, /landing-hero-mockup/);
  assert.match(source, /landing-mockup-panel/);
  assert.match(source, /命 盘 档 案/);
  assert.match(source, /对 话/);
});

test('Trust metrics render as ruled grid (top + bottom rule, dividers between)', () => {
  const css = fs.readFileSync(new URL('../src/styles/landing.css', import.meta.url), 'utf8');
  assert.match(css, /\.landing-trust-grid[\s\S]*?border-top:\s*1px solid/);
  assert.match(css, /\.landing-trust-grid[\s\S]*?border-bottom:\s*1px solid/);
  assert.match(css, /\.landing-metric[\s\S]*?border-right:\s*1px solid/);
});

test('Landing is responsive at 900px (mockup stacks, gallery wraps)', () => {
  const css = fs.readFileSync(new URL('../src/styles/landing.css', import.meta.url), 'utf8');
  assert.match(css, /@media[^{]+max-width:\s*900px/);
  assert.match(css, /\.landing-hero-mockup[\s\S]*?grid-template-columns:\s*1fr/);
});

test('CosmicCardPreview uses versioned PNG illustrations without raw bazi terms', () => {
  const source = fs.readFileSync(new URL('../src/components/landing/CosmicCardPreview.jsx', import.meta.url), 'utf8');
  const illustrations = fs.readFileSync(new URL('../src/components/landing/landingIllustrations.jsx', import.meta.url), 'utf8');
  const art = fs.readFileSync(new URL('../src/lib/cardArt.js', import.meta.url), 'utf8');
  assert.match(illustrations, /bamboo/);
  assert.match(illustrations, /samoye/);
  assert.match(illustrations, /lamp/);
  assert.match(illustrations, /puffer/);
  assert.match(illustrations, /dandelion/);
  assert.match(source, /src=\{illustrationSrc\}/);
  assert.match(source, /loading="eager"/);
  assert.match(source, /decoding="async"/);
  assert.doesNotMatch(source, /loading="lazy"/);
  assert.match(art, /CARD_ART_VERSION/);
  assert.match(art, /\\?v=/);
  assert.doesNotMatch(source, /[>\s]日主[<\s]/);
  assert.doesNotMatch(source, /[>\s]格局[<\s]/);
});

test('PersonaMarquee eagerly loads animated static illustrations', () => {
  const source = fs.readFileSync(new URL('../src/components/landing/LandingHome.jsx', import.meta.url), 'utf8');
  const personaBlock = source.match(/function PersonaMarquee\(\)[\s\S]*?export function LandingHome/)?.[0] || '';

  assert.match(personaBlock, /loading="eager"/);
  assert.match(personaBlock, /decoding="async"/);
  assert.doesNotMatch(personaBlock, /loading="lazy"/);
});

test('HepanCardPreview shows editorial pair card with label, state copy, and cta', () => {
  const source = fs.readFileSync(new URL('../src/components/landing/HepanCardPreview.jsx', import.meta.url), 'utf8');
  const css = fs.readFileSync(new URL('../src/styles/landing.css', import.meta.url), 'utf8');
  assert.match(source, /撑腰搭子/);
  assert.match(source, /绽放 × 蓄力/);
  assert.match(source, /\{category\}/);
  assert.match(source, /你冲，我在后面把灯留着/);
  assert.match(source, /cardIllustrationSrc/);
  assert.match(source, /landing-hepan-pair-art/);
  assert.match(source, /<img/);
  assert.match(source, /loading="eager"/);
  assert.doesNotMatch(source, /loading="lazy"/);
  assert.doesNotMatch(source, /<svg/);
  assert.match(css, /\.landing-hepan-illust[\s\S]*aspect-ratio:\s*1\.2\s*\/\s*1/);
  assert.match(css, /\.landing-hepan-pair-side-a/);
  assert.match(css, /\.landing-hepan-pair-side-b/);
});
