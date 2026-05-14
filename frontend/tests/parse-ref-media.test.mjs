import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

import { parseRef } from '../src/lib/parseRef.js';
import { ATMOSPHERE_ASSETS, pickAtmosphereAsset } from '../src/lib/mediaCard.js';

test('media questions render only one primary media card for repeated movie tokens', () => {
  const segments = parseRef(
    '你这盘像 [[movie:肖申克的救赎|弗兰克·德拉邦特]]。\n\n后面又像 [[movie:肖申克|1994]] 里的坚持。',
    { context: '用一部电影形容我这盘' },
  );

  const media = segments.filter((s) => s.type === 'media');
  assert.equal(media.length, 1);
  assert.equal(media[0].title, '肖申克的救赎');
  assert.equal(media[0].subtitle, '弗兰克·德拉邦特');
  assert.match(
    segments.map((s) => s.value || s.title || '').join(''),
    /《肖申克》里的坚持/,
  );
});

test('bare chart refs are repaired before rendering so internal ids do not leak', () => {
  const segments = parseRef(
    '今年liunian.2026|丙午和明年liunian.2027|丁未，都在你当前dayun.1|戊午运（18-27岁）的后半段。',
    { context: '接下来两年的关键节点' },
  );

  const refs = segments.filter((s) => s.type === 'ref');
  assert.deepEqual(
    refs.map((s) => [s.id, s.label]),
    [
      ['liunian.2026', '丙午'],
      ['liunian.2027', '丁未'],
      ['dayun.1', '戊午运'],
    ],
  );
  assert.doesNotMatch(segments.map((s) => s.value || s.label || '').join(''), /liunian\.2026\|丙午|dayun\.1\|戊午/);
});

test('ordinary chart answers degrade explicit media tokens to inline titles', () => {
  const segments = parseRef(
    '这不是惩罚，是锻造的逻辑。就像 [[movie:爆裂鼓手|达米恩·查泽雷]] 里那种关系。',
    { context: '这盘命的底色是什么' },
  );

  assert.equal(segments.filter((s) => s.type === 'media').length, 0);
  assert.match(
    segments.map((s) => s.value || s.title || '').join(''),
    /就像 《爆裂鼓手》 里那种关系/,
  );
});

test('media cards require the requested kind instead of rendering mismatched tokens', () => {
  const segments = parseRef(
    '如果硬要说电影，是 [[movie:爆裂鼓手|达米恩·查泽雷]]，但歌更贴。',
    { context: '用一首歌形容我这盘' },
  );

  assert.equal(segments.filter((s) => s.type === 'media').length, 0);
  assert.match(
    segments.map((s) => s.value || s.title || '').join(''),
    /《爆裂鼓手》/,
  );
});

test('short movie follow-ups can still render movie cards', () => {
  const segments = parseRef(
    '那换成 [[movie:心灵捕手|格斯·范·桑特]]。',
    { context: '换一部' },
  );

  const media = segments.filter((s) => s.type === 'media');
  assert.equal(media.length, 1);
  assert.equal(media[0].kind, 'movie');
  assert.equal(media[0].title, '心灵捕手');
});

test('natural movie questions rescue quoted titles into cards', () => {
  const segments = parseRef(
    '要找一个电影形容你现在的情绪模式，我会想到《海上钢琴师》。',
    { context: '我的情绪模式像哪个电影' },
  );

  const media = segments.filter((s) => s.type === 'media');
  assert.equal(media.length, 1);
  assert.equal(media[0].kind, 'movie');
  assert.equal(media[0].title, '海上钢琴师');
});

test('classics titles in song answers are never rescued into song cards', () => {
  // 真实 bug：AI 在"用一首歌形容我"的回答里，先引古籍 《穷通宝鉴》——1985，
  // 段落末尾才给出真歌 《山丘》。rescueQuotedTitles 只 rescue 第一个 《X》，
  // 结果古籍标题被渲染成歌曲卡（穷通宝鉴 · 1985 + 网易云搜索）。
  const segments = parseRef(
    '论三秋甲木：《穷通宝鉴》——1985 里说，丁火为尊。\n\n所以如果用一首歌形容你，我会选《山丘》。',
    { context: '用一首歌形容我' },
  );

  const media = segments.filter((s) => s.type === 'media');
  assert.equal(media.length, 1, 'should render exactly one song card');
  assert.equal(media[0].kind, 'song');
  assert.equal(media[0].title, '山丘');
  // 《穷通宝鉴》依然作为文字保留下来，不被吃掉
  const flat = segments.map((s) => s.value || s.title || '').join('');
  assert.match(flat, /《穷通宝鉴》/);
  assert.doesNotMatch(flat, /穷通宝鉴.*1985.*网易云/);
});


test('every classics title in repo is protected from the song/movie rescue', () => {
  // 仓库里的 5 本古籍 + 几个其他常被 LLM 引用的命理古籍，全部跳过 rescue。
  // 单独成段也不应该被错误识别成歌曲。
  const classics = ['穷通宝鉴', '三命通会', '滴天髓', '渊海子平', '子平真诠', '神峰通考', '命理探源', '子平粹言'];
  for (const name of classics) {
    const segs = parseRef(
      `《${name}》里讲，秋木要见火。我会选《山丘》。`,
      { context: '用一首歌形容我' },
    );
    const media = segs.filter((s) => s.type === 'media');
    assert.equal(media.length, 1, `${name}: 应仅渲染 1 张卡（山丘），实际 ${media.length}`);
    assert.equal(media[0].title, '山丘', `${name}: 卡应是山丘，实际 ${media[0].title}`);
  }
});


test('media questions prefer explicit media tokens over rescuing quoted titles', () => {
  const segments = parseRef(
    '先想到《老伴》。真正推荐 [[song:老伴|李荣浩]]，它的节奏更贴。',
    { context: '用一首歌形容我这盘' },
  );

  const media = segments.filter((s) => s.type === 'media');
  assert.equal(media.length, 1);
  assert.equal(media[0].kind, 'song');
  assert.equal(media[0].title, '老伴');
  assert.equal(media[0].subtitle, '李荣浩');
  assert.match(segments.map((s) => s.value || '').join(''), /先想到《老伴》/);
});

test('weather scent and book tokens are no longer rendered as cards', () => {
  // 这三类卡片在上线前精简掉了：素材库风格不统一、价值密度低，
  // 不再出现在落地页和对话里。LLM 即使误生成 token 也不应渲染。
  const weather = parseRef(
    '你现在像 [[weather:雨后初雾|慢下来，光会回来]]。',
    { context: '用一种天气形容我现在的状态' },
  );
  assert.equal(weather.filter((s) => s.type === 'media').length, 0);

  const scent = parseRef(
    '这盘像 [[scent:冷茶白花|雨后石板 · 淡淡焚香]]。',
    { context: '用一种气味形容我这盘' },
  );
  assert.equal(scent.filter((s) => s.type === 'media').length, 0);

  const book = parseRef(
    '推荐 [[book:夜读手记|凡事都有定时]]。',
    { context: '推荐一本书让我读懂自己' },
  );
  assert.equal(book.filter((s) => s.type === 'media').length, 0);
});

test('media dedupe state prevents later paragraphs from rescuing a duplicate quoted title', () => {
  const mediaState = new Set();
  const first = parseRef(
    '最像 [[movie:一一|杨德昌]]。',
    { context: '我的情绪模式像哪个电影', mediaState },
  );
  const second = parseRef(
    '还有一层更深的：《一一》的片长很慢。',
    { context: '我的情绪模式像哪个电影', mediaState },
  );

  assert.equal(first.filter((s) => s.type === 'media').length, 1);
  assert.equal(second.filter((s) => s.type === 'media').length, 0);
  assert.match(second.map((s) => s.value || s.title || '').join(''), /《一一》的片长/);
});

test('flower tokens render one restrained semantic card without duplicate cards', () => {
  const segments = parseRef(
    '这盘像 [[flower:雨后玉兰|清白、慢开，有一点冷香]]，也有 [[flower:山茶|藏着热度]]。',
    { context: '用一种花形容我这盘' },
  );

  const media = segments.filter((s) => s.type === 'media');
  assert.equal(media.length, 1);
  assert.equal(media[0].kind, 'flower');
  assert.equal(media[0].title, '雨后玉兰');
  assert.equal(media[0].subtitle, '清白、慢开，有一点冷香');
  assert.match(
    segments.map((s) => s.value || s.title || '').join(''),
    /《山茶》/,
  );
});

test('flower card stays restrained and avoids 桃花运 false trigger', () => {
  const flowerChat = parseRef(
    '今年桃花运会不会好一点？',
    { context: '感情怎么看' },
  );
  assert.equal(flowerChat.filter((s) => s.type === 'media').length, 0);
});

test('semantic flower card stays local and non-clickable', () => {
  const mediaHelpers = fs.readFileSync(new URL('../src/lib/mediaCard.js', import.meta.url), 'utf8');
  const mediaCard = fs.readFileSync(new URL('../src/components/MediaCard.jsx', import.meta.url), 'utf8');

  assert.match(mediaHelpers, /if \(kind !== 'song' && kind !== 'movie'\) return null/);
  assert.match(mediaCard, /const isSemanticCard = kind === 'flower'/);
  assert.match(mediaCard, /if \(!safeTitle \|\| isSemanticCard\)/);
  assert.match(mediaCard, /const CardTag = url \? 'a' : 'div'/);
  assert.match(mediaCard, /url[\s\S]*href:\s*url[\s\S]*role:\s*'group'/);
  assert.match(mediaCard, /pickAtmosphereAsset\(kind,\s*safeTitle,\s*displaySub\)/);
  assert.match(mediaCard, /--media-atmosphere/);
});

test('semantic card atmosphere pool has multiple assets and keyword matching', () => {
  assert.equal(ATMOSPHERE_ASSETS.flower.length, 8);

  assert.equal(pickAtmosphereAsset('flower', '雨后玉兰', '清白冷香')?.id, 'rain-magnolia');
  assert.equal(pickAtmosphereAsset('flower', '半开芍药', '正在聚拢力气')?.id, 'half-peony');
  assert.equal(pickAtmosphereAsset('flower', '夜山茶', '暗红但克制')?.id, 'night-camellia');
  assert.equal(pickAtmosphereAsset('flower', '鸢尾纸影', '淡紫粉感')?.id, 'iris-paper');
  assert.equal(pickAtmosphereAsset('flower', '雨后玉兰', '清白冷香')?.colors.length, 2);

  const fallbackA = pickAtmosphereAsset('flower', '柔软的灰蓝', '需要慢下来')?.id;
  const fallbackB = pickAtmosphereAsset('flower', '柔软的灰蓝', '需要慢下来')?.id;
  assert.equal(fallbackA, fallbackB);
});

test('movie cards use a local cinematic fallback without replacing real posters', () => {
  const mediaCard = fs.readFileSync(new URL('../src/components/MediaCard.jsx', import.meta.url), 'utf8');
  const css = fs.readFileSync(new URL('../src/index.css', import.meta.url), 'utf8');

  assert.equal(ATMOSPHERE_ASSETS.movie.length, 8);
  assert.equal(pickAtmosphereAsset('movie', '海上钢琴师', '孤独的船与琴声')?.id, 'night-reading');
  assert.equal(pickAtmosphereAsset('movie', '花样年华', '王家卫')?.id, 'sunset-glow');
  assert.match(mediaCard, /const isAtmosphereCard = \['flower', 'movie'\]\.includes\(kind\)/);
  assert.match(mediaCard, /kind !== 'movie' \|\| !cover\?\.url/);
  assert.match(mediaCard, /cover\?\.url \? \(/);
  assert.match(css, /\.media-card-movie::before[\s\S]*var\(--media-atmosphere\)/);
  assert.doesNotMatch(css, /\.media-card-movie \.media-card-cta[\s\S]*display:\s*none/);
});

test('chat media card text column can shrink instead of overlapping the action chip', () => {
  const css = fs.readFileSync(new URL('../src/index.css', import.meta.url), 'utf8');
  const cardRule = css.match(/\.media-card\s*\{[\s\S]*?\n\s*\}/)?.[0] || '';
  const metaRule = css.match(/\.media-card-meta\s*\{[\s\S]*?\n\s*\}/)?.[0] || '';
  const titleRule = css.match(/\.media-card-title\s*\{[\s\S]*?\n\s*\}/)?.[0] || '';
  const subRule = css.match(/\.media-card-sub\s*\{[\s\S]*?\n\s*\}/)?.[0] || '';
  const ctaRule = css.match(/\.media-card-cta\s*\{[\s\S]*?\n\s*\}/)?.[0] || '';

  assert.match(cardRule, /grid-template-columns:\s*56px\s+minmax\(0,\s*1fr\)\s+auto/);
  assert.match(cardRule, /box-sizing:\s*border-box/);
  assert.match(metaRule, /min-width:\s*0/);
  assert.match(titleRule, /text-overflow:\s*ellipsis/);
  assert.match(titleRule, /white-space:\s*nowrap/);
  assert.match(subRule, /text-overflow:\s*ellipsis/);
  assert.match(subRule, /white-space:\s*nowrap/);
  assert.match(ctaRule, /white-space:\s*nowrap/);
});

test('flower cards use local atmosphere images and hide search affordance', () => {
  const mediaCard = fs.readFileSync(new URL('../src/components/MediaCard.jsx', import.meta.url), 'utf8');
  const css = fs.readFileSync(new URL('../src/index.css', import.meta.url), 'utf8');

  assert.match(mediaCard, /flower:\s*'✽'/);
  assert.match(mediaCard, /const isAtmosphereCard = \['flower', 'movie'\]\.includes\(kind\)/);
  assert.match(mediaCard, /atmosphereAsset\?\.colors/);
  assert.match(mediaCard, /--media-glow-a/);
  assert.match(css, /\.media-card-flower::before[\s\S]*var\(--media-atmosphere\)/);
  assert.match(css, /\.media-card-flower::before[\s\S]*filter:\s*blur/);
  assert.match(css, /\.media-card-flower::after[\s\S]*--media-glow-a/);
  assert.match(css, /\.media-card-flower \.media-card-cta[\s\S]*display:\s*none/);
});
