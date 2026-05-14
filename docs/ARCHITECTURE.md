# 架构详解

补充 [README](../README.md) 的「架构总览」，把每一层的设计权衡讲清楚。

---

## 1. 设计原则

1. **真实命理计算与 LLM 严格分离**
   命盘排盘、十神力量、格局识别、用神判断、行运评分等所有"有正确答案"的计算，全部落在 `paipan/` 这个纯 Python 引擎里，有 632 个 pytest 守住边界。LLM 只负责"把这些结构化事实组织成人话"。

2. **古籍引用走真本检索，不让模型自由发挥**
   `classics/` 目录里是穷通宝鉴、子平真诠、滴天髓、三命通会、渊海子平、周易共 6 部经典的真本文本。任何引用都要经过 retrieval 层召回后才能进 prompt。

3. **prompt 是代码，不是字符串**
   prompt 被切成 `style / context / router / expert / shard / anchor` 等十多个文件，按 intent 动态拼装；像组件树一样可单独测试、替换、版本化。

4. **流式优先**
   所有面向用户的长文回答都走 SSE，避免"转圈圈等几十秒"的 UX。所有断流、续写、停止、重答、截断都有对应 handler。

5. **逐步演进、保留旧版本**
   `retrieval2` 还在跑（claim-level BM25 + LLM selector），`retrieval3` 是新做的（家族化确定性查询）。新旧共存，灰度切换。

---

## 2. 后端分层

```
┌────────────────────────────────────────────────────────┐
│  api/                  HTTP 边界                         │
│  ├─ auth.py            短信 / 注册 / 游客 / 头像        │
│  ├─ charts.py          命盘 CRUD + 总论 + 板块 + 大运   │
│  ├─ conversations.py   会话 + 流式消息 + 起卦           │
│  ├─ card.py            单人分享卡                       │
│  ├─ hepan.py           合盘邀请漏斗                     │
│  ├─ billing.py         订阅 / 支付 webhook              │
│  ├─ media.py           歌曲 / 电影封面抓取 + 取色       │
│  ├─ tracking.py        前端事件埋点                     │
│  ├─ admin.py           运营后台                         │
│  ├─ quota.py           当日额度                         │
│  └─ wx.py              微信 JS-SDK 签名                 │
└────────────────────────────────────────────────────────┘
                          │
┌────────────────────────────────────────────────────────┐
│  services/             业务编排（事务、权限、LLM 流）    │
│  ├─ chart.py / chart_llm.py                            │
│  ├─ conversation_chat.py  ★ 主聊天 SSE 编排            │
│  ├─ conversation_gua.py    起卦                         │
│  ├─ conversation_memory.py 上下文滑窗 + 分页            │
│  ├─ chat_router.py         意图路由（fast LLM + kw fallback）│
│  ├─ paipan_adapter.py      调 paipan 引擎               │
│  ├─ classics_polisher.py   古书定调（persona / verdict 双池）│
│  ├─ card/                  分享卡生成 / 预览 / 导出     │
│  ├─ hepan/                 合盘邀请 / 解读 / 对话       │
│  ├─ quota.py + subscription.py                         │
│  └─ event.py               用户事件                     │
└────────────────────────────────────────────────────────┘
                          │
┌────────────────────────────────────────────────────────┐
│  models/               SQLAlchemy ORM                  │
│  ├─ user.py            phone_hash / dek_ciphertext / 游客│
│  ├─ chart.py           缓存 + 命盘元数据                │
│  ├─ conversation.py    会话 + cursor 分页元数据         │
│  ├─ message.py         消息（含 streaming 状态）        │
│  ├─ hepan_invite.py / hepan_message.py                 │
│  ├─ subscription.py    订阅档位 / 状态机                │
│  ├─ event.py           运营事件                         │
│  └─ llm_usage_log.py   每次 LLM 调用的 token 计量       │
└────────────────────────────────────────────────────────┘
```

---

## 3. 命盘引擎（paipan）

独立 Python package，通过 `services/paipan_adapter.py` 调用。设计上完全不依赖 LLM、不依赖数据库，纯函数式输入输出。

### 核心模块

```
paipan/paipan/
├── compute.py        入口：输入 (年, 月, 日, 时, 分, 经纬度) → 完整命盘对象
├── solar_time.py     真太阳时校正（经度差 + 均时差）
├── china_dst.py      中国历史夏令时（1986-1991）
├── zi_hour.py        子时派别（早子 / 晚子 / 不分）
├── analyzer.py       综合分析：十神 + 力量 + 格局 + 用神 + 行运 一站式
├── li_liang.py       十神力量（含天透地藏、月令、虚透、得令失令）
├── force.py          force 计算（用于 K 线能量曲线）
├── ge_ju.py          格局识别（飞天禄马、倒冲、井栏叉、朝阳格 …）
├── he_ke.py          合冲刑害会（含三合局、半合、暗合）
├── yongshen.py + yongshen_data.py    用神三法（调候 / 格局 / 扶抑）+ transmutation
├── xingyun.py + xingyun_data.py      大运/流年 5-bin 评分 + cross interaction
└── cities.py         全球城市经纬度 + 时区
```

### Plan 7.x 引擎完整体（2026-04 完成）

| Plan | 主题 | 实质 |
|---|---|---|
| 7.3 | 用神 engine v1 三法合成 | 把"调候/格局/扶抑"三派合成出 primary + secondary 用神 |
| 7.4 | 行运 engine 5-bin | 大运/流年分极弱/弱/中/强/极强 5 档，配合用神算节奏 |
| 7.5a | 静态用神变化 | 命局自身合局触发的用神 transmutation |
| 7.5b | 动态用神变化 | 大运/流年触发的 transmutation |
| 7.6 | engine polish deep | 5-bin 极弱/极强边界处理 + weighted average |
| 7.7 | cross interaction | 大运与流年的相互作用计算 |

完成后 LLM 输出从"推测/可能/或许"满天飞，变成可以"用神是某某，因为某某；这十年关键是某某"的具体推理。

---

## 4. AI 编排细节

### 4.1 主聊天链路

`services/conversation_chat.py` 是主入口，伪代码如下：

```python
async def stream_reply(conv_id, user_msg):
    # 1. 加锁，防止同会话并发（用 Redis 分布式锁）
    async with conv_lock(conv_id):

        # 2. 持久化 user message（先存，断网也不丢）
        await persist_user_message(conv_id, user_msg)

        # 3. 取上下文（滑窗 + 分页 anchor）
        history = await load_recent_messages(conv_id, limit=N)
        chart = await load_chart_for_conv(conv_id)

        # 4. 意图路由（fast LLM, temp=0, json mode）
        intent_info = await chat_router.classify(user_msg, chart, history)
        # intent_info = {intent, reason, retrieval_focus, answer_plan, ...}

        # 5. 古籍证据组合（确定性 retriever + LLM selector）
        evidence = await retrieval3.compose(
            chart, intent_info.intent, intent_info.retrieval_focus
        )

        # 6. 构造 expert prompt
        prompt = expert.build(
            chart=compact_chart_context(chart),
            evidence=evidence,
            intent=intent_info,
            history=history,
            user_msg=user_msg,
        )

        # 7. 流式调用（primary，失败 fallback）
        full = ""
        async for event in llm.chat_stream_with_fallback(prompt, tier="primary"):
            yield event_to_sse(event)
            if event.type == "delta":
                full += event.text

        # 8. 持久化 assistant message + usage log
        await persist_assistant_message(conv_id, full, usage=event.usage)
```

### 4.2 SSE 事件协议

```
event: model    data: {"modelUsed": "<name>"}
event: delta    data: {"text": "..."}
event: delta    data: {"text": "..."}
…
event: done     data: {"full": "...", "tokens_used": 123, "finish_reason": "stop"}
```

前端 `frontend/src/lib/sse.js` 用 `fetch` + `ReadableStream` 解析（不用 `EventSource`，因为后者不支持 POST + headers）。

### 4.3 router 与 keyword fallback

`prompts/router.py` 给 router LLM 一个 json schema，让它返回：

```json
{
  "intent": "relationship",
  "reason": "用户问感情运",
  "retrieval_focus": "正缘/桃花",
  "artifact": null,
  "answer_plan": "先讲日支配偶宫，再讲伴侣星，最后给大运提示"
}
```

LLM 失败（超时 / 解析错 / 异常）时退到 `KEYWORD_FALLBACK` 字典，按关键词命中拍 intent，保证主链路永远 100% 不中断。

### 4.4 Retrieval3 家族化

```python
# server/app/retrieval3/composer.py 大意
def compose(chart, intent, focus) -> list[EvidenceCard]:
    cards = []

    # 确定性查表：穷通宝鉴 + 三命通会卷 8/9
    if intent in QTBJ_INTENTS:
        cards += qtbj_lookup(chart.day_pillar, chart.month)
    if intent in SMTH89_INTENTS:
        cards += smth89_lookup(chart.day_pillar, chart.hour)

    # 涉及合化关系
    if has_hehua(chart):
        cards += hehua_retriever(chart)

    # 用户消息提到神煞 / 格局 / 六亲
    if mentions_shensha(user_msg):
        cards += shensha_retriever(user_msg)
    if intent == "special_geju" or mentions_geju(user_msg):
        cards += geju_retriever(user_msg, chart)
    if mentions_liuqin(user_msg, intent):
        cards += liuqin_retriever(user_msg)

    # 外貌 / 性情
    if intent in ("appearance", "personality"):
        cards += appearance_retriever(chart)

    # 理论 fallback：子平真诠 / 滴天髓 / 渊海子平
    if not cards or intent in THEORY_INTENTS:
        cards += theory_retriever(chart, intent, focus)  # LLM selector + BM25

    return dedupe_and_trim(cards, max=8)
```

每个 retriever 都是独立模块，可单独 unit test。

### 4.5 prompt loader 与 shard 缓存

```python
# server/app/prompts/loader.py 大意
@lru_cache(maxsize=None)
def load_shard(intent: str) -> str:
    p = REPO_ROOT / "shards" / f"{intent}.md"
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""

@lru_cache(maxsize=1)
def load_skill() -> str:
    return (REPO_ROOT / "docs" / "skills" / "SKILL.md").read_text()

@lru_cache(maxsize=1)
def load_conversation_guide() -> str:
    return (REPO_ROOT / "docs" / "skills" / "conversation-guide.md").read_text()
```

进程启动后每个文件只读一次，开发时改 shard 重启即可。

---

## 5. 数据模型重点

```
users                  phone_hash, phone_last4, dek_ciphertext (E2E), wechat_*, guest_token
charts                 owner_user_id, birth_*, paipan_json, polish_persona, polish_verdict
conversations          chart_id, user_id, title, last_cursor
messages               conv_id, role, content, status (streaming/done/aborted/truncated),
                       meta (intent, retrieval_focus, evidence_anchors, suggestions, model)
hepan_invite           inviter_user_id, slug, a_chart_id, b_chart_id?, status
hepan_messages         hepan_id, role, content
subscriptions          user_id, tier (lite/standard/pro), expires_at, provider, raw_event
quota_logs             user_id, day, used
events                 user_id, type, payload (运营事件)
llm_usage_logs         model, prompt_tokens, completion_tokens, latency_ms, conv_id?, chart_id?
```

**E2E 加密**：用户手机号用 user-level DEK 加密存 `dek_ciphertext`，DEK 本身用 KEK（环境变量 `ENCRYPTION_KEK`，64 hex）加密。即使 DB 整库泄漏也拿不到明文手机号——除非同时拿到 KEK。

---

## 6. 前端架构

### 6.1 路由

```
/                LandingHome              # 扇形卡片入场 + 卖点 + CTA
/app             AppShell                 # 登录后壳层（侧边会话列表 + 内容区）
  /app/chart     Chart                    # 命盘四柱 + 十神 + 大运 + 流年
  /app/chat      Chat                     # 多轮对话主界面
  /app/kline     KLineChart               # 命局能量曲线
/card/:slug      CardScreen               # 单人分享卡预览
/hepan/mine      MyHepanPage              # 我的合盘列表
/hepan/:slug     HepanScreen              # 合盘漏斗
/pricing         PricingPage              # 订阅
/admin           AdminDashboard           # 后台
/legal/:slug    LegalPage                 # 隐私 / 协议
```

### 6.2 状态管理

Zustand 切片：

```
useUserStore        当前用户 + 会话 token
useChartStore       命盘列表 + 当前命盘
useConversationStore  会话列表 + 当前会话 + 消息列表（含 streaming 增量）
useHepanStore       合盘
useSubscriptionStore 订阅状态
useUIStore          全局 UI 状态（modal、loading、toast）
```

streaming 时把 delta 直接 append 到当前 message，UI 用 `useSyncExternalStore` 拿增量。

### 6.3 关键工程点

- **html2canvas 导出图修复 oklch**：现代 CSS 颜色用 `oklch()` 提升对比一致性，但 html2canvas 不认识 → 导出前先把所有 `oklch()` 转 `rgb()`（`frontend/src/lib/exportImage.js`）
- **K 线能量曲线**：`frontend/src/components/kline/`，5-bin 评分曲线 + tooltip clamp + bar 三色 band + 主导十神角标
- **IME 拼音兼容**：拼音输入时回车不触发发送（`compositionstart/compositionend` flag）
- **viewport-gated 动画**：扇形卡片用 IntersectionObserver 触发 deal-in，进屏才动，省电省 CPU

---

## 7. 测试策略

### Paipan（632 tests）

每个核心函数都有 golden case + 边界 case：

- 真太阳时：北京/纽约/UTC+0/南半球各取一组
- 子时派别：23:30 在三派下各自的输出
- 历史夏令时：1988-04-10 北京（DST 开始日）
- 十神力量：含月令、得令、虚透、藏干透干等多种状态
- 格局：每个特殊格局至少一组正例 + 一组反例
- 用神三法：调候/格局/扶抑各自 corner case
- 行运 5-bin：极弱 ↔ 极强 ↔ 中庸的过渡

### Server（439 tests）

- API 层：每个端点 happy path + 鉴权失败 + 限额触发
- LLM client：mock SSE，覆盖 fallback、timeout、truncate、abort 各路径
- Retrieval：固定 chart + 固定 query → 固定 evidence 集合
- 数据库：用 testcontainers 起真 PostgreSQL，不 mock
- 订阅状态机：状态转换 + 边界（过期/续费/降级）全覆盖

### Frontend（51 tests）

node:test 跑工具函数 + 关键 reducer + format 函数。组件 UI 走人工/截图验证（`.claire/` 本地存截图，不入仓）。

---

## 8. 已知技术债 & 演进路线

- **conversation streaming hold DB**：当前 streaming 期间 message 行被一直 hold，1000+ 并发会爆。需要 refactor 成"streaming 写 Redis、done 才写 PG"
- **classics 索引版本化**：`classics/` 改动后要重跑 `scripts/build_classics_index.py`，没自动 hook
- **Retrieval2 / Retrieval3 双轨**：retrieval2 在某些 fallback 路径仍被调用，应当全面切到 retrieval3
- **agent loop 实验未上**：曾在 `claude/modest-faraday-946e30` 分支做过 tool-calling agent loop（ChartDossier / UserProfile / memory_store），最终因"路由 + 检索"已经够用未合并主线，留作未来探索
- **当前没上多模态生图**：作为后续 roadmap，可能用 nano-banana 给"命运卡"加生成图（JD 加分项之一）

---

## 9. 给读者的指引

如果你是面试方想快速看到代码亮点：

1. `server/app/llm/client.py` —— SSE 流式 + primary/fallback 双模型
2. `server/app/services/conversation_chat.py` —— 主聊天编排
3. `server/app/services/chat_router.py` + `prompts/router.py` —— 意图路由 + keyword fallback
4. `server/app/retrieval3/composer.py` —— 8 类 retriever 家族化组合
5. `server/app/prompts/expert.py` + `shards/core.md` —— prompt 组装与 shard 系统
6. `paipan/paipan/yongshen.py` + `xingyun.py` —— Plan 7.x 命理引擎核心
7. `deploy/nginx.conf` + `deploy/PRODUCTION.md` —— 生产部署清单
8. `frontend/src/components/Chat.jsx` + `lib/sse.js` —— 流式 UI 实现

如果你想了解协作开发的方式：

- `docs/release-notes/` —— 每个 Plan 的发布说明，可以看到 spec → plan → implementation 的完整链路
- commit 历史里 `claude/*` 前缀的分支基本对应一个独立工作流
