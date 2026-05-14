# 有时 · YouShi BaZi

> 一款理性派的八字 AI 应用。
> **品牌**：「有时」——双关「命有其时」与「有时间」。
> **线上**：https://youshi.app
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

> 截图保留在线上版本，README 中暂以文字呈现。访问 https://youshi.app 直接体验。

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

### Vibe 思路

1. **byte-level 引经据典**：不让 LLM 编出"古书有云"，所有引用都来自 `classics/` 真本，引用要带书名 + 卷次 + 原文
2. **去 hedging**：早期 LLM 输出充斥"或许 / 可能 / 推测"，shard + intent guide 强约束让回答变成"用神是 X，因为 Y；大运壬寅这十年的关键是 Z"
3. **像朋友画白板**：所有意图统一约束 4-12 行短回答，不是百科条目
4. **反 MBTI / 反鸡汤**：personality shard 明确禁止 16 型人格风格输出
5. **conversation-guide**：何时澄清、何时深入、何时反问、何时承认不知道——单独一份 runtime 加载的对话指南

更详细的方法论：[ARCHITECTURE.md](docs/ARCHITECTURE.md) 第 5 节。

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
sudo certbot --nginx -d youshi.app -d www.youshi.app
```

### DNS 配置（域名 → 服务器）

```
youshi.app          A     <server-ip>     TTL 600
www.youshi.app      A     <server-ip>     TTL 600
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
curl https://youshi.app/api/health                       # {"status":"ok",...}
curl -I https://youshi.app/assets/index-*.js | grep -i cache-control
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

## AI 协作开发说明

整个项目用 **Claude Code** 做主要开发工具。流程上：

1. **plan-first**：复杂特性先在 `docs/superpowers/` 落 spec → plan → checklist，确认后再 implementation
2. **TDD discipline**：新功能（特别是 paipan 引擎）先写 pytest 用例再写实现，632 + 439 测试基本上都是这样积累出来的
3. **commit per slice**：每个可独立 review 的小切片一个 commit，commit message 用 `feat / fix / chore / refactor / docs` 前缀 + 中文短描述
4. **multi-worktree 并行**：用 `git worktree` 同时开 2-3 个分支处理独立特性（如 retrieval3 重建 + chat 续写体验互不阻塞）
5. **回归保护**：每个修复都补对应单测，避免 LLM 协作产生的"看起来对了其实改坏"

---

## 联系

- 项目作者：陈松辉
- Email: songhuichen7@gmail.com
- 在线 demo: https://youshi.app

---

## License

MIT —— 见 [LICENSE](LICENSE)。

部分 prompt、shard、运营策略文档未包含在本仓库（属项目核心资产，已脱敏剥离）。如果你是面试方需要看完整代码，邮件联系开授权。
