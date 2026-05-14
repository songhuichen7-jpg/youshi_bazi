import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const loaderUrl = new URL('../src/components/ClassicsBookLoader.jsx', import.meta.url);
const panelUrl = new URL('../src/components/ClassicsPanel.jsx', import.meta.url);
const cssUrl = new URL('../src/index.css', import.meta.url);

function readSource(url) {
  return fs.readFileSync(url, 'utf8');
}

test('ClassicsPanel delegates pending animation to ClassicsBookLoader', () => {
  const source = readSource(panelUrl);

  assert.match(source, /import\s+ClassicsBookLoader\s+from\s+['"]\.\/ClassicsBookLoader['"]/);
  assert.match(source, /<ClassicsBookLoader\s+isSlow=\{isSlow\}\s*\/>/);
  assert.doesNotMatch(source, /const\s+BOOKS\s*=\s*\[/);
});

test('ClassicsBookLoader uses page-flip and cleans up animation resources', () => {
  const source = readSource(loaderUrl);

  assert.match(source, /import\s+\{\s*PageFlip\s*\}\s+from\s+['"]page-flip['"]/);
  assert.match(source, /import\s+['"]page-flip\/src\/Style\/stPageFlip\.css['"]/);
  assert.match(source, /new\s+PageFlip\(/);
  assert.match(source, /flipNext\(/);
  assert.match(source, /destroy\(\)/);
  assert.match(source, /clearInterval\(/);
  assert.match(source, /clearTimeout\(/);
});

test('ClassicsBookLoader keeps the loading state accessible and motion-safe', () => {
  const source = readSource(loaderUrl);

  assert.match(source, /role="status"/);
  assert.match(source, /aria-label="正在翻检古籍"/);
  assert.match(source, /aria-hidden="true"/);
  assert.match(source, /prefers-reduced-motion/);
  assert.match(source, /古籍较厚，再翻一会儿/);
  assert.match(source, /正在翻阅古籍/);
});

test('ClassicsBookLoader preserves the accepted real pageflip geometry', () => {
  const source = readSource(loaderUrl);
  const css = readSource(cssUrl);

  assert.match(source, /const\s+PAGE_WIDTH\s*=\s*280;/);
  assert.match(source, /const\s+PAGE_HEIGHT\s*=\s*340;/);
  assert.match(source, /minWidth:\s*240/);
  assert.match(source, /maxWidth:\s*PAGE_WIDTH/);
  assert.match(source, /minHeight:\s*292/);
  assert.match(source, /maxHeight:\s*PAGE_HEIGHT/);
  assert.match(css, /\.classics-pageflip-host\s*\{[^}]*position:\s*relative;/s);
  assert.match(css, /\.classics-pageflip-host\s*\{[^}]*width:\s*560px;/s);
  assert.match(css, /\.classics-pageflip-host\s*\{[^}]*height:\s*340px;/s);

  const hostRule = css.match(/\.classics-pageflip-host\s*\{(?<body>[^}]*)\}/s)?.groups?.body || '';
  assert.doesNotMatch(hostRule, /position:\s*absolute/);
  assert.doesNotMatch(hostRule, /left:\s*50%/);
  assert.doesNotMatch(hostRule, /top:\s*50%/);
  assert.doesNotMatch(hostRule, /translate\(-50%,\s*-50%\)/);
});

test('ClassicsBookLoader rebuilds page DOM before PageFlip initialization', () => {
  const source = readSource(loaderUrl);

  assert.match(source, /function\s+buildPageFlipNodes/);
  assert.match(source, /className="classics-pageflip-mount"/);
  assert.match(source, /const\s+host\s*=\s*document\.createElement\(['"]div['"]\)/);
  assert.match(source, /host\.className\s*=\s*['"]classics-pageflip-host['"]/);
  assert.match(source, /host\.replaceChildren\(\s*\.\.\.buildPageFlipNodes\(BOOKS\[index\]\)\s*\)/);
  assert.match(source, /mount\.replaceChildren\(host\)/);

  const rebuildIndex = source.indexOf('host.replaceChildren');
  const initIndex = source.indexOf('new PageFlip(host');
  const loadIndex = source.indexOf('pageFlip.loadFromHTML');

  assert.ok(rebuildIndex > -1, 'expected the host DOM to be rebuilt from book data');
  assert.ok(initIndex > rebuildIndex, 'PageFlip must initialize after fresh page nodes exist');
  assert.ok(loadIndex > rebuildIndex, 'PageFlip must load freshly rebuilt page nodes');
});

test('ClassicsBookLoader keeps the book title on the front cover only', () => {
  const source = readSource(loaderUrl);

  assert.match(source, /function\s+buildEndleafNode/);
  assert.match(source, /<EndleafPage\s*\/>/);
  assert.match(source, /\.\.\.book\.pages\.map\(\(page,\s*pageIndex\)\s*=>\s*buildTextPageNode\(page,\s*pageIndex\)\),\s*buildEndleafNode\(\)/s);
  assert.equal(source.match(/buildCoverNode\(book,\s*true\)/g)?.length, 1);
  assert.doesNotMatch(source, /buildCoverNode\(book\),\s*\]/);
});
