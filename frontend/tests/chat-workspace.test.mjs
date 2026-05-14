import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

import { buildChatWorkspace, mergePromptChips } from '../src/lib/chatWorkspace.js';


test('buildChatWorkspace default state: AI opener uses chart facts + three actionable chips', () => {
  const workspace = buildChatWorkspace({
    meta: {
      rizhu: '甲戌',
      dayStrength: '身弱',
      geju: '食神格',
      yongshen: '木',
    },
    dayun: [],
    dayunOpenIdx: null,
    liunianOpenKey: null,
    verdicts: { status: 'done' },
  });

  assert.equal(workspace.contextLabel, null);
  assert.equal(workspace.title, '命盘已经排好了');
  assert.deepEqual(workspace.badges, ['甲戌 · 身弱', '食神格', '用神 木']);

  // AI 开口一句：第一帧让 AI 先用盘里的事实说话，而不是递菜单
  assert.ok(workspace.openingLine, 'openingLine should exist');
  assert.match(workspace.openingLine.headline, /甲戌/);
  assert.match(workspace.openingLine.headline, /食神格/);
  assert.match(workspace.openingLine.body, /整体/);
  assert.match(workspace.openingLine.body, /具体/);

  // 三 chip：每个有 label + prompt，prompt 能直接当 send() 参数
  assert.ok(Array.isArray(workspace.openingChips));
  assert.equal(workspace.openingChips.length, 3);
  for (const chip of workspace.openingChips) {
    assert.ok(typeof chip.label === 'string' && chip.label.length > 0, 'chip.label non-empty');
    assert.ok(typeof chip.prompt === 'string' && chip.prompt.length > 0, 'chip.prompt non-empty');
  }
  // 默认态保留：实务（关键节点）、隐喻（一首歌）、自察（警觉）三种入口
  const labels = workspace.openingChips.map((c) => c.label).join(' / ');
  assert.match(labels, /关键节点|节点/);
  assert.match(labels, /一首歌|歌/);
  assert.match(labels, /警觉|该避|留心/);

  // 八条 bullet 教学清单已下线
  assert.equal(workspace.openingGuide, undefined);

  // starterQuestions 是输入框上方的快捷问题区，与开场无关，保持不变
  assert.deepEqual(workspace.starterQuestions.slice(0, 3), [
    '这盘像哪部电影',
    '这盘的核心矛盾',
    '接下来两年的关键节点',
  ]);
});


test('buildChatWorkspace dayun state: opener and chips reference the open dayun step', () => {
  const workspace = buildChatWorkspace({
    meta: { rizhu: '甲戌' },
    dayun: [
      { age: 8, gz: '己未', ss: '正财/正财', years: [] },
      { age: 18, gz: '戊午', ss: '偏财/伤官', years: [] },
    ],
    dayunOpenIdx: 1,
    liunianOpenKey: null,
    verdicts: { status: 'done' },
  });

  assert.equal(workspace.contextLabel, '戊午大运');
  assert.equal(workspace.title, '戊午大运');
  assert.deepEqual(workspace.badges, ['18岁起', '偏财/伤官']);
  assert.equal(workspace.starterQuestions[0], '这十年的主线');

  // AI 开场提到当前大运
  assert.ok(workspace.openingLine);
  assert.match(workspace.openingLine.headline, /戊午/);

  // chip 锁在"这十年"语境
  assert.equal(workspace.openingChips.length, 3);
  const labels = workspace.openingChips.map((c) => c.label).join(' / ');
  assert.match(labels, /十年|主线/);
});


test('buildChatWorkspace liunian state: opener and chips reference the open year', () => {
  const workspace = buildChatWorkspace({
    meta: { rizhu: '甲戌' },
    dayun: [
      { age: 18, gz: '戊午', ss: '偏财/伤官', years: [{ year: 2014, gz: '甲午', ss: '比肩' }] },
    ],
    dayunOpenIdx: 0,
    liunianOpenKey: '0-0',
    verdicts: { status: 'done' },
  });

  assert.equal(workspace.contextLabel, '2014 甲午');
  assert.equal(workspace.title, '2014 甲午');
  assert.deepEqual(workspace.badges, ['所属 戊午大运', '比肩']);
  assert.equal(workspace.starterQuestions[0], '这一年最大的机会');

  // AI 开场提到具体年份
  assert.ok(workspace.openingLine);
  assert.match(workspace.openingLine.headline, /2014/);

  // chip 锁在"这一年"语境
  assert.equal(workspace.openingChips.length, 3);
  const labels = workspace.openingChips.map((c) => c.label).join(' / ');
  assert.match(labels, /这一年|机会|压力/);
});


test('mergePromptChips keeps context-first ordering and removes duplicates', () => {
  const chips = mergePromptChips(
    ['这张盘的核心矛盾是什么', '接下来两年重点看什么'],
    ['接下来两年重点看什么', '我适合什么伴侣', '先看整体主线'],
    4,
  );

  assert.deepEqual(chips, [
    '这张盘的核心矛盾是什么',
    '接下来两年重点看什么',
    '我适合什么伴侣',
    '先看整体主线',
  ]);
});


test('empty chat welcome renders an AI opener + 3 starter chips, no bullet wall', () => {
  const source = fs.readFileSync(new URL('../src/components/Chat.jsx', import.meta.url), 'utf8');

  // 容器仍叫 chat-opening-guide（外层 pull-quote 样式复用）
  assert.match(source, /chat-opening-guide/);

  // AI 一句开场：headline + body 由 workspace.openingLine 提供
  assert.match(source, /workspace\.openingLine/);

  // 三 chip 接 workspace.openingChips，单击 send(chip.prompt)
  assert.match(source, /workspace\.openingChips/);
  assert.match(source, /chip\.prompt/);

  // 旧实现不再出现：8 条 bullet 列表 + 教学化 closing
  assert.doesNotMatch(source, /chat-opening-list/);
  assert.doesNotMatch(source, /chat-opening-closing/);
  assert.doesNotMatch(source, /chat-guide-grid/);
  assert.doesNotMatch(source, /chat-guide-btn/);
});


test('placeholder rotation is paced to be readable (>= 8s/句) and skips repeats per session', () => {
  const source = fs.readFileSync(new URL('../src/components/Chat.jsx', import.meta.url), 'utf8');
  const examples = fs.readFileSync(new URL('../src/lib/chatPromptExamples.js', import.meta.url), 'utf8');

  // 节奏：4s 改成 ≥ 8s。具体常量挂在 chatPromptExamples 这边便于调。
  const intervalMatch = examples.match(/PROMPT_ROTATE_INTERVAL_MS\s*=\s*(\d+)/);
  assert.ok(intervalMatch, 'PROMPT_ROTATE_INTERVAL_MS should be defined');
  assert.ok(Number(intervalMatch[1]) >= 8000, `rotation interval should be >= 8000ms, got ${intervalMatch[1]}`);

  // focus 中暂停：textarea 挂 onFocus/onBlur，inputFocused 进 placeholderRotating 条件
  assert.match(source, /const \[inputFocused, setInputFocused\] = useState\(false\)/);
  assert.match(source, /onFocus=\{\(\) => setInputFocused\(true\)\}/);
  assert.match(source, /onBlur=\{\(\) => setInputFocused\(false\)\}/);
  assert.match(source, /placeholderRotating\s*=\s*!busy\s*&&\s*!input\s*&&\s*!activeContextLabel\s*&&\s*!inputFocused/);

  // 同一会话不重复：用 ref 维护已展示索引集合，全展示完才 reset
  assert.match(source, /shownExampleIdxRef/);
});


test('empty state opens with a 800ms "reading the chart" beat before the headline', () => {
  const source = fs.readFileSync(new URL('../src/components/Chat.jsx', import.meta.url), 'utf8');
  const css = fs.readFileSync(new URL('../src/index.css', import.meta.url), 'utf8');

  // 状态机：chartReading 标志位 + 每个 conversation 只播一次的 ref
  assert.match(source, /const \[chartReading, setChartReading\] = useState\(false\)/);
  assert.match(source, /readingShownConvRef/);

  // 800ms 定时器
  assert.match(source, /setChartReading\(true\)/);
  assert.match(source, /setTimeout\(\(\) => setChartReading\(false\), 800\)/);

  // 入场态 UI：dot + 文字
  assert.match(source, /chat-opening-reading/);
  assert.match(source, /正在读这张盘/);

  // 揭幕态用专属容器（带 keyframe 动画），不污染 hepan 分支
  assert.match(source, /chat-opening-reveal/);

  // CSS：keyframes 落到 index.css
  assert.match(css, /@keyframes\s+chat-opening-reading-in/);
  assert.match(css, /@keyframes\s+chat-opening-reveal-in/);
  assert.match(css, /@keyframes\s+chat-opening-pulse/);
});


test('chat turns expose edit and regenerate controls', () => {
  const source = fs.readFileSync(new URL('../src/components/Chat.jsx', import.meta.url), 'utf8');

  assert.match(source, /prepareChatRegeneration/);
  assert.match(source, /editingUserIndex/);
  assert.match(source, /修改问题/);
  assert.match(source, /重新回答/);
});


test('chat waiting state uses animated thinking indicator instead of trace receipts', () => {
  const source = fs.readFileSync(new URL('../src/components/Chat.jsx', import.meta.url), 'utf8');

  assert.match(source, /ThinkingIndicator/);
  assert.doesNotMatch(source, /ChatReceipts/);
  assert.doesNotMatch(source, /TraceReceipt/);
});

test('chat sends force the conversation to follow the newest streamed answer', () => {
  const source = fs.readFileSync(new URL('../src/components/Chat.jsx', import.meta.url), 'utf8');

  assert.match(source, /forceFollowNextRender/);
  assert.match(source, /shouldForceFollowRef/);
  assert.match(source, /settleFollowToBottom/);
  assert.match(source, /requestAnimationFrame/);
});

test('chat follow-up chips live under the latest answer and fill the composer', () => {
  const source = fs.readFileSync(new URL('../src/components/Chat.jsx', import.meta.url), 'utf8');
  const css = fs.readFileSync(new URL('../src/index.css', import.meta.url), 'utf8');

  assert.match(source, /className="chat-followups"/);
  assert.match(source, /const showFollowups = isLast && !streaming && !!m\.content && followupChips\.length >= 2/);
  assert.match(source, /onClick=\{\(\) => selectFollowup\(chip\)\}/);
  assert.match(source, /function selectFollowup\(chip\)/);
  assert.match(source, /setInput\(text\)/);
  assert.match(source, /inputRef\.current\?\.focus\(\)/);
  assert.doesNotMatch(source, /send\(chip\)/);
  assert.doesNotMatch(source, /className="chat-chips"/);
  assert.match(css, /\.chat-followups\s*\{/);
  assert.match(css, /\.chat-followup-chip\s*\{/);
  assert.doesNotMatch(css, /\.chat-jump-bottom\[data-above-chips='true'\]/);
});

test('chat layout keeps a single internal scroll area so the composer stays visible', () => {
  const css = fs.readFileSync(new URL('../src/index.css', import.meta.url), 'utf8');

  assert.match(css, /\.right-pane\s*\{[^}]*overflow:\s*hidden/s);
  assert.match(css, /\.chat-body\s*\{[^}]*min-height:\s*0/s);
  assert.match(css, /\.chat-input-wrap\s*\{[^}]*flex:\s*0 0 auto/s);
  assert.match(css, /\.chat-input textarea\s*\{[^}]*min-height:\s*26px/s);
});
