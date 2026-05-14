# 有时 · YouShi BaZi

> 一款理性派的八字 AI 应用。
> **品牌**：「有时」——双关「命有其时」与「有时间」。
> **线上**：https://youshi.fun
> **定位**：排盘引擎 + 古籍真本检索 + 流式 LLM 多轮对话 + 梅花易数起卦

不是另一个把生辰八字塞给 GPT 让它瞎编的工具。
所有命理计算走自研 Python 引擎，所有古籍引用走真本检索，LLM 只负责组织、解释、追问。

---

## 截图 / 演示

| 命盘工作台 | 多轮对话 + 古籍证据 |
|---|---|
| 四柱 / 十神 / 大运 / 流年 + 命局能量 K 线 | 用户提问 → 意图路由 → 古籍检索 → 流式解读 |

| 分享卡（单人） | 合盘邀请 |
|---|---|
| Specimen 风格命盘卡，html2canvas 一键导出 | A 生成分享链接 → B 填完落地 → 双方流式合盘解读 |

> 截图保留在线上版本，README 中暂以文字呈现。访问 https://youshi.fun 直接体验。

---

## 我做了什么（一句话版）

一个人独立完成的全栈 AI 应用：

- **后端**：FastAPI + SQLAlchemy 2.0 + PostgreSQL，10+ 业务模块、34 个 alembic migration、439 个测试
- **排盘引擎**：自研 Python package，4255 行纯计算，632 个测试，覆盖四柱排盘、十神力量、格局识别、用神三法合成、大运流年 5-bin 评分
- **前端**：React 19 + Vite + Zustand，工作台 + 聊天 + 落地页 + 后台 + 合盘邀请漏斗
- **AI 编排**：SSE 流式 + 15 类意图路由 + 8 类古籍 retriever 家族化检索 + primary/fallback 双模型降级
- **运维**：Docker（腾讯云 Lighthouse）+ nginx 反代 + Certbot HTTPS + systemd + alembic 自动迁移
- **协作模式**：Claude Code 重度 vibe 编程用户，全程 AI pair-programming 完成，commit message 全程 plan-first

---

## 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│  Browser (React 19 + Vite + Zustand)                         │
│    ├─ /                  LandingHome（扇形卡片入场动画）        │
│    ├─ /app/chart         命盘工作台 + 命局能量 K 线           │
│    ├─ /app/chat          多轮对话 + 古籍面板 + 起卦            │
│    ├─ /card/:slug        单人分享卡（Specimen 风格 + 导出图）  │
│    ├─ /hepan/:slug       合盘邀请 → 填写 → 解读 → 对话         │
│    └─ /pricing /admin    订阅 / 运营后台                       │
└────────────────────────────┬─────────────────────────────────┘
                             │ HTTPS（nginx + Certbot）
                             │ SSE 长连接（proxy_buffering off, 300s timeout）
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI Server                                              │
│                                                              │
│  HTTP 边界  ──────  api/  (auth / charts / conversations /    │
│                          card / hepan / billing / admin …)   │
│                                                              │
│  业务编排  ──────  services/  (事务、权限、LLM 编排)           │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Chat Pipeline（多轮对话主链路）                      │    │
│  │                                                     │    │
│  │   user_msg                                          │    │
│  │      ↓                                              │    │
│  │   ChatRouter (fast LLM, temp=0)                     │    │
│  │      ↓  → intent ∈ {relationship, career, timing,   │    │
│  │              wealth, personality, health, dayun_    │    │
│  │              step, liunian, divination, … 15 类}    │    │
│  │      ↓  keyword fallback（LLM 故障兜底）             │    │
│  │   ConversationMemory（滑窗 + 持久化）                │    │
│  │      ↓                                              │    │
│  │   compact_chart_context（命盘 → 结构化字段，token   │    │
│  │      ↓                  友好压缩）                    │    │
│  │   Retrieval3 Composer（8 类家族化 retriever）        │    │
│  │      ↓                                              │    │
│  │   Expert Prompt（core shard + intent shard +        │    │
│  │      ↓        命盘 + 古籍 evidence + intent guide）  │    │
│  │   LLM Stream（primary → fallback，SSE delta 推前端）│    │
│  │      ↓                                              │    │
│  │   持久化（messages 表 + LLM usage log）              │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Paipan Engine  ─  纯 Python，零依赖外调，632 测试            │
│    四柱排盘 / 十神力量 / 格局 / 用神三法 / 行运 5-bin / 合冲会刑 │
└────────────────────────────┬─────────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  PostgreSQL                                                  │
│   users / charts / conversations / messages / hepan_invite / │
│   hepan_messages / subscriptions / events / llm_usage_logs   │
└──────────────────────────────────────────────────────────────┘
```

更详细的版本：[ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## AI 调用逻辑（JD 核心关注点）

### 1. 流式响应 (SSE)

**位置**：`server/app/llm/client.py` + `server/app/llm/events.py`

封装了一个 OpenAI-compatible 的异步流式客户端 `chat_stream_with_fallback()`，输出格式：

```jsonc
{"type":"model","modelUsed":"<primary-model>"}    // 首 delta 抵达时下发
{"type":"delta","text":"..."}                     // 文本增量，N 次
{"type":"done","full":"...",
 "tokens_used":123,"prompt_tokens":50,
 "completion_tokens":73,
 "finish_reason":"stop"}                          // 收尾，带 usage
{"type":"error","code":"...","message":"..."}     // 异常
```

工程上踩过的坑都补在客户端里：

- **首 delta timeout**：长时间无数据视为模型卡死，主动降级到 fallback
- **finish_reason 截断处理**：模型 length 截断后，前端拿到 "接着写" 按钮，复用同一会话上下文继续
- **主动停止后续写**：用户中途打断 → 写半句的状态持久化 → 再点继续走相同链路
- **重答去重**：UI 触发"重新回答"不会产生重复 user message
- **生成中允许继续输入**：流式过程中 textarea 仍可打字，停止后再发

### 2. 多模型路由 & token 成本

```
tier="primary"  →  LLM_MODEL          （主回答，思考强度高、上下文长）
               →  LLM_FALLBACK_MODEL  （主模型失败兜底）

tier="fast"     →  LLM_FAST_MODEL      （router / chips / 短结构化任务）
```

OpenAI-compatible 协议，已切换过 DeepSeek / MiMo / OpenAI 三家。客户端用双 header（`Authorization: Bearer` + `api-key`）做 provider-neutral 兼容，换 provider 改两行环境变量即可。

成本控制：

- 命盘 → `compact_chart_context()` 压缩为紧凑结构化字段，不丢真本字段名
- Router 走 fast tier 而不是 primary（成本差 5-10x）
- Shard 用 `@lru_cache` 加载，单次启动只读一次磁盘
- `llm_usage_logs` 表持久化每次调用的 prompt/completion tokens，方便事后审计

### 3. 工具调用 / Function-calling 风格的检索编排

虽然没有用 OpenAI 原生的 `tools=[...]` 接口（八字场景的工具调用本质是确定性查询，函数调用模型路由反而引入幻觉），但实现了**等价的家族化 retriever 调度器**：

`server/app/retrieval3/composer.py` 中按 intent 把 8 类 retriever 组合调用，每个 retriever 像一个"工具"：

| Retriever | 触发 | 数据源 | 调用方式 |
|---|---|---|---|
| QtbjLookup | meta / verdict / career / wealth … | 穷通宝鉴调候表 | 10×12 确定性查表 |
| Smth89Lookup | 同上 | 三命通会卷 8/9 日时诀 | 60×12 确定性查表 |
| Hehua | 涉及合化关系 | 地支合化规则 | 干支关系检测 |
| Shensha | 神煞关键词 | 神煞词库 | 别名子串匹配 |
| Geju | 特殊格局 | 格局词库 | 别名子串匹配 |
| Liuqin | 六亲 | 六亲关系库 | 别名子串匹配 |
| Appearance | appearance / personality | 三命通会"性情相貌" | 子串匹配 |
| TheoryFallback | career / wealth / relationship … | 子平真诠 / 滴天髓 / 渊海子平 | LLM selector → BM25 |

确定性 retriever 零幻觉；LLM-selector retriever 二次 LLM 调用做高精度过滤。Composer 负责去重 + 截断 8 张 EvidenceCard 注入 expert prompt。

### 4. 上下文管理

- **会话级**：`services/conversation_memory.py` 滑窗 + 数据库分页（"老消息往上翻"用 cursor + scroll anchor）
- **命盘级**：`prompts/context.py` 把 paipan 完整输出压缩成结构化上下文（十神符号 / 分数 / 用神 / 格局 / 大运流年），既 token 友好又便于 LLM 引用具体字段
- **Skill 注入**：`docs/skills/SKILL.md` + `docs/skills/conversation-guide.md` 在 runtime 加载，作为"知识库序言"嵌入 prompt
- **跨轮一致性**：router 输出的 `retrieval_focus` 与上一轮的 evidence 在 prompt 中保留 anchor，避免来回跳话题

---

## 关键 Prompt 与 Vibe 思路

> 完整 prompt 是项目核心资产，README 只描述设计思路，不贴原文。

### Prompt 分层

```
server/app/prompts/
├── style.py        全局世界观 + 古籍引用契约 + 输出风格预设
├── context.py      paipan 命盘 → 紧凑结构化上下文
├── router.py       意图路由分类器（15 intent + keyword fallback）
├── expert.py       主对话 expert prompt 组装器
├── verdicts.py     命局总论（一次性长文）
├── sections.py     7 个板块（性格 / 事业 / 财 / 感情 / 婚恋 / 健康 / 医疗）
├── dayun_step.py   单步大运展开
├── liunian.py      流年解读
├── chips.py        追问建议自动生成（每轮 3 个 chip）
├── gua.py          梅花易数起卦解读
└── anchor.py       古籍引用锚点规范化
```

### Shard 系统（intent-specific prompt 片段）

```
shards/
├── core.md            始终加载，描述输出风格 + 引用纪律
├── personality.md     人物画像类
├── relationship.md    感情 / 婚恋 / 配偶宫
├── career.md          事业 / 格局 / 官杀食伤
├── wealth.md          财 / 食伤生财链路
├── health.md          健康 / 医疗
├── appearance.md      外貌 / 性情
├── timing.md          大运 / 流年 / 具体岁数
├── meta.md            概念解释
└── special_geju.md    特殊格局（飞天禄马 / 倒冲 …）
```

`expert.py` 拼装顺序：

```
system role
+ style.py (世界观 + 引用契约)
+ shards/core.md
+ shards/<intent>.md            ← 按 router 输出 intent 条件加载
+ compact_chart_context(chart)  ← 命盘结构化字段
+ evidence_cards (8 张)         ← retrieval3 注入的古籍真本片段
+ INTENT_GUIDE[intent]          ← 15 种 intent 的聚焦方向约束
+ history (recent N messages)
+ user_message
```

### Prompt 设计原则（产品 prompt）

1. **byte-level 引经据典**：不让 LLM 编出"古书有云"，所有引用都来自 `classics/` 真本，引用要带书名 + 卷次 + 原文
2. **去 hedging**：早期 LLM 输出充斥"或许 / 可能 / 推测"，shard + intent guide 强约束让回答变成"用神是 X，因为 Y；大运壬寅这十年的关键是 Z"
3. **像朋友画白板**：所有意图统一约束 4-12 行短回答，不是百科条目
4. **反 MBTI / 反鸡汤**：personality shard 明确禁止 16 型人格风格输出
5. **conversation-guide**：何时澄清、何时深入、何时反问、何时承认不知道——单独一份 runtime 加载的对话指南

更详细的方法论：[ARCHITECTURE.md](docs/ARCHITECTURE.md) 第 5 节。

---

## Vibe Coding 思路（开发方法论）

> 这一节讲我**怎么和 Claude Code 协作**完成这个项目——是 vibe coding 的工作流，不是产品 prompt 的设计。

整个项目 90%+ 的代码由 Claude Code（Opus / Sonnet）vibe 编程产出，我作为 architect + reviewer。下面是踩出来、且每天还在用的几条规则：

### 1. Plan-first，不 plan 不写代码

复杂特性必须先落三件东西，再开 implementation：

```
docs/superpowers/<topic>/
├── spec.md         先把"要解决什么问题、不解决什么、边界在哪"写清楚
├── plan.md         再把"分几步、每步 acceptance criteria 是什么"写清楚
└── checklist.md    最后把"代码层面要动哪些文件、写哪些测试"列出来
```

只有 checklist 全部勾选 = feature done。这条规则把"vibe 出来一堆看似 work 实际埋雷"的风险压到最低。每个 Plan 7.x 子版本（命理引擎跃升）都是这样跑的——见 `docs/release-notes/2026-04-21-plan-7.x-*.md`。

> ⚠️ `docs/superpowers/` 在公开仓库中已脱敏（属于内部规划文档），但 `docs/release-notes/` 完整保留——里面能看到 spec → plan → 实施过程的完整轨迹。

### 2. TDD 是底线，不是装饰

Paipan 引擎 632 个测试、Server 439 个测试，**绝大多数都是先写测试再写实现**。
LLM 协作最大的风险是"它给的代码看起来对、跑起来也对、但改坏了别的"——只有红/绿/重构循环能压住这个风险。

具体做法：

- **写新功能**：先让 Claude 写出 pytest 用例 + golden case，我 review 测试是否真的测到了关键路径，再让它写实现
- **修 bug**：先写一个能复现 bug 的失败测试，再让 Claude 改实现把它变绿。这样修复后这个 bug 永远不会回归
- **重构**：用现有测试做 safety net，重构完跑 632 + 439 + 51 全套，绿了才合并

### 3. Multi-worktree 并行开发

复杂项目同时有 2-3 个独立特性在进展时，用 `git worktree` 给每个特性开独立工作目录：

```bash
git worktree add ../bazi-retrieval3 claude/retrieval3-rebuild
git worktree add ../bazi-chat-resume claude/chat-resume-experience
```

每个 worktree 跑独立的 Claude Code 会话，互不阻塞主分支。retrieval3 重建（8 个 retriever 家族化）和 chat 续写体验（流式停止/重答/截断）就是这样**同一周内并行落地**的。

### 4. Commit-per-slice + Conventional prefix

每个**能独立 review 的最小切片**一个 commit。commit message 强约束：

```
feat(chart): 拉高命局能量图绘图区
fix(card): 单卡/合盘卡"保存为图"被 oklch 卡死 — 渲染前先把色值转 rgb 再喂 html2canvas
chore(eval): 把 hehua 接入 phase_a eval 框架
refactor(retrieval): 拆 retrieval3.composer 的家族化调度
docs: 更新系统架构文档至 2026-05-12 现状
```

好处：

- `git log --oneline` 直接当 release notes 用
- 出问题 `git bisect` 能秒级定位
- AI review 时上下文清晰，不会把 5 个无关变更打包成"看起来都对"

### 5. 回归保护永远先行

LLM 协作最隐蔽的失败模式：**"我刚才让你修 A，你顺手把 B 改坏了，因为 B 没测试。"**
对策有两条：

1. **每个修复都附测试**：哪怕只是 1 个 unit test，先确认它能复现这个失败，再让 Claude 改
2. **改完跑全套**：`npm run test`（632 + 439 + 51 = 1122 测试），绿了才 commit

### 6. 用 AI 做 second opinion，不让一个 AI 拍板

关键设计、关键算法、关键 bug 用**两套上下文**评审一遍：

- 主开发用 Claude Code
- 复杂决策点用 Codex CLI 做一次独立 review（`/codex:rescue` 风格的盲评）
- 偶尔互相 catch 出对方 miss 的边界 case

这条对 Plan 7.x 命理引擎（涉及大量边界判断：极弱/极强/中庸/transmutation/cross interaction）尤其有效。

### 7. Skills / 知识库工程化

项目中**人能写的方法论文档，都写成 LLM 也能直接读懂的格式**：

- 命理方法论 → `docs/skills/SKILL.md`，runtime 加载到 LLM prompt
- 对话节奏约束 → `docs/skills/conversation-guide.md`，runtime 加载
- 古籍引用路径表 → `docs/skills/classical-references.md`
- 项目里坑过的 bug 模式 → `docs/skills/synthesizer-bug-prevention.md`

这些既是 LLM 在 runtime 用的知识库，也是我开 Claude Code 会话时让它读的"项目入门 onboarding"。一份文档，两个用户。

### 8. 不藏分支历史

`git log --all` 看得到 `claude/<topic>-<hash>` 风格的实验分支——失败的尝试不删，让它和成功路径一起留在历史里。比如曾在 `claude/modest-faraday-946e30` 分支试过 tool-calling agent loop，跑下来发现"router + 检索"已经够用且更稳定，于是没合主线，但分支保留。

---



## 部署（DNS / HTTPS / 监控）

### 单机最小可上线（2 vCPU / 4 GB RAM）

```bash
# 1. 服务器准备（以腾讯云 Lighthouse Ubuntu 22.04 为例）
sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx \
  postgresql-14 redis-server

# 2. 代码 + 依赖
git clone https://github.com/<you>/youshi-bazi /opt/youshi
cd /opt/youshi/server
uv sync && uv run alembic upgrade head

# 3. 配置环境变量
cp .env.example .env && vim .env
# 必填：LLM_API_KEY / DATABASE_URL / REDIS_URL / ENCRYPTION_KEK
# ENCRYPTION_KEK 用 `python -c "import secrets; print(secrets.token_hex(32))"`

# 4. systemd 起后端
sudo cp deploy/uvicorn.service /etc/systemd/system/youshi.service
sudo systemctl daemon-reload && sudo systemctl enable --now youshi

# 5. 前端构建
cd ../frontend && npm ci && npm run build

# 6. nginx 反代 + SSL
sudo cp deploy/nginx.conf /etc/nginx/sites-available/youshi
sudo ln -s /etc/nginx/sites-available/youshi /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d youshi.fun -d www.youshi.fun
```

### DNS 配置（域名 → 服务器）

```
youshi.fun          A     <server-ip>     TTL 600
www.youshi.fun      A     <server-ip>     TTL 600
```

注册商解析生效后 → certbot 自动签 Let's Encrypt 证书 → nginx 把 `80` redirect 到 `443`。

### HTTPS / nginx 要点

`deploy/nginx.conf` 关键配置：

- **HTTPS 重定向**：`80 → 443`
- **静态资源长缓存**：`/assets/`、`/static/` 加 ETag + 1 年 `Cache-Control`
- **API 反代**：`/api/` → `http://127.0.0.1:3101`
- **SSE 长连接**：`proxy_buffering off`、`proxy_read_timeout 300s`、关闭 gzip（避免缓冲整段流）
- **HSTS**：`Strict-Transport-Security: max-age=63072000; includeSubDomains`

### 验收清单

```bash
curl https://youshi.fun/api/health                       # {"status":"ok",...}
curl -I https://youshi.fun/assets/index-*.js | grep -i cache-control
# 浏览器开 DevTools EventStream，发条 > 30s 的长问题，看 chunk 不被切断
redis-cli MONITOR | grep -E "rl:|lock:"                  # 多 worker 锁验证
```

### 监控（最小三件套）

- **探活**：UptimeRobot 5 分钟探一次 `/api/health`
- **错误日志**：`journalctl -u youshi`，grep `ERROR|Traceback`
- **PG 慢查询**：`log_min_duration_statement = 500` → 慢于 500ms 的 SQL 落盘

### 扩容路径

按当前架构扛得住 ~100 同时活跃用户、~15 同时聊天。再大需要：

1. 多机 + nginx upstream + sticky session（Redis 已经是共享的，OK）
2. PG 读写分离，读走 replica
3. SSE 释放 DB（消除 streaming 中的 long transaction）
4. LLM API key pool 轮询，突破单 key RPM 限制

详见：[DEPLOY.md](docs/DEPLOY.md)

---

## 项目结构

```
.
├── frontend/                React 19 + Vite + Zustand
│   ├── src/
│   │   ├── components/      AppShell / Chart / Chat / Card / Hepan / KLine / Landing
│   │   ├── lib/             api / analytics / kline / format / media
│   │   ├── store/           Zustand
│   │   └── styles/
│   └── tests/               node:test 51 个
│
├── server/                  FastAPI + SQLAlchemy 2.0
│   ├── app/
│   │   ├── api/             HTTP 边界（10+ 路由模块）
│   │   ├── auth/            鉴权 / 权限 / 限额依赖
│   │   ├── billing/         订阅 / 支付 webhook
│   │   ├── core/            config / db / crypto / rate_limit / distributed_lock
│   │   ├── data/            内置卡片 / 合盘 / 媒介数据
│   │   ├── llm/             OpenAI-compatible client + SSE events + usage logs
│   │   ├── models/          SQLAlchemy ORM
│   │   ├── prompts/         11 类提示词组装
│   │   ├── retrieval2/      claim-level BM25 + LLM selector
│   │   ├── retrieval3/      家族化 retriever + composer
│   │   ├── schemas/         Pydantic
│   │   └── services/        业务编排
│   ├── alembic/             34 个 migration
│   └── tests/               pytest 439 个（含 testcontainers PostgreSQL）
│
├── paipan/                  纯 Python 排盘 + 命理引擎
│   ├── paipan/
│   │   ├── compute.py       四柱 / 十神 / 纳音 / 大运 / 流年
│   │   ├── analyzer.py      命局综合分析
│   │   ├── li_liang.py      十神力量度量
│   │   ├── ge_ju.py         格局识别
│   │   ├── he_ke.py         合 / 冲 / 刑 / 害 / 会
│   │   ├── yongshen.py      用神三法（调候 / 格局 / 扶抑）
│   │   ├── xingyun.py       大运 / 流年 5-bin 评分 + cross interaction
│   │   ├── solar_time.py    真太阳时
│   │   ├── zi_hour.py       子时派别处理
│   │   └── china_dst.py     历史夏令时
│   └── tests/               pytest 632 个
│
├── classics/                古籍真本（穷通宝鉴 / 子平真诠 / 滴天髓 / 三命通会 / 渊海子平 / 周易）
├── shards/                  intent-specific prompt 片段（10 个）
├── docs/                    架构 / release notes / skill 方法论
├── deploy/                  Dockerfile / docker-compose / nginx / systemd
└── package.json             根脚本（dev / build / test）
```

---

## 本地开发

```bash
# 安装依赖
uv sync                       # Python（paipan + server，workspace）
cd frontend && npm ci         # 前端

# 两个终端跑开发服
npm run dev:back              # FastAPI + reload at :3101
npm run dev:front             # Vite HMR at :5173，/api 自动代理到 :3101

# 一键跑（构建前端后由后端托管）
npm run start                 # http://localhost:3101
```

### 测试

```bash
npm run test:paipan           # 632 tests
npm run test:server           # 439 tests（需 docker，跑 testcontainers PG）
npm run test:frontend         # 51 tests
npm run test                  # 全部
```

---

## 技术栈选型说明

| 选型 | 原因 |
|---|---|
| **FastAPI** | 异步原生、Pydantic schema、SSE 友好、Python 生态丰富（pandas / numpy 处理命理数据方便） |
| **SQLAlchemy 2.0 async** | 与 FastAPI 异步无缝，typed model 减少 schema drift |
| **PostgreSQL** | 复杂 JSONB 字段（命盘缓存、消息元数据）查询便利；alembic 工具链成熟 |
| **Redis** | 分布式速率限制 + 会话锁 + 缓存层（媒介封面） |
| **React 19** | Suspense / use() / Action 在长流式 UI 上比 18 顺手 |
| **Zustand** | 比 Redux 轻、TypeScript 友好、不像 Recoil 那样把数据耦合到组件树 |
| **OpenAI-compatible LLM** | 客户端写一次，DeepSeek / MiMo / OpenAI 都能切；后期可上多 provider 路由 |
| **uv** | Python 包管理速度 ~10× pip；workspace 让 paipan + server 共用依赖一目了然 |
| **Docker + 腾讯云 Lighthouse** | 国内访问稳定、价格友好、Docker 一行 deploy |

---

## 联系

- 项目作者：陈松辉
- Email: songhuichen7@gmail.com
- 在线 demo: https://youshi.fun

---

## License

MIT —— 见 [LICENSE](LICENSE)。

部分 prompt、shard、运营策略文档未包含在本仓库（属项目核心资产，已脱敏剥离）。如果你是面试方需要看完整代码，邮件联系开授权。
