/** Rotating placeholder examples for the chat input.
 *
 *  Mix of metaphor / time / personality / relationship / practical questions.
 *  The mix is deliberate: the metaphor ones (歌曲、电影、画、菜) teach new
 *  users that this tool reads like a person, not a query box; the practical
 *  ones (换工作 / 矛盾 / 用神) anchor what the panel actually answers.
 */
export const PROMPT_EXAMPLES = [
  // 艺术类比
  '我的感情用一首歌，你会选哪首',
  '这张盘像哪部电影',
  '用一幅画形容我',
  '用一道菜形容我',
  '用一首唐诗概括我',
  // 时间节奏
  '我的人生进度条到哪了',
  '这两年的关键词是什么',
  '用一句歌词总结今年',
  '我现在处在故事的第几章',
  // 人格反差
  '我跟别人最大的不同是什么',
  '我天生会什么、做什么会别扭',
  '别人眼里我是什么样的人',
  '我是水做的还是火做的',
  '我命里的「必修课」和「选修课」是什么',
  // 关系感情
  '我谈恋爱像什么',
  '我跟父母是哪种相处模式',
  '我适合什么样的爱情节奏',
  // 实务保留
  '这两年我适合换工作吗',
  '这盘的核心矛盾在哪',
  '我适合自己干还是体制内',
  '我父亲是什么样的人',
  '用神什么时候能用上',
];

// 4s 太快 — 用户还没读完一句就翻页，placeholder 反而像在催。9s 是
// 默读一句完整中文短句、再停顿一两秒"决定要不要用"的节奏。
export const PROMPT_ROTATE_INTERVAL_MS = 9000;
