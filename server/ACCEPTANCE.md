# server Backend — Acceptance Checklist

Plan 2 (Foundation) + Plan 3 (Auth Business) + Plan 4 (Charts CRUD + paipan) +
Plan 5 (Chart LLM SSE + Quota + Recompute) 合并状态。

## Hard Gates

- [x] **全部测试并行全绿**
  - `uv run --package server pytest server/tests/ -n auto`
  - Result: **309 passed in 19.9s** → ✅
- [x] **源码覆盖率 ≥ 85%**
  - `uv run --package server pytest --cov=app --cov-config=/dev/null server/tests/`
  - Result: **85%** → ✅
- [x] **并行 CI runtime < 60s** — Wall time: **19.9s** → ✅
- [x] **wheel 可装可跑** — 24 业务路由 (health + 7 auth + 2 sessions + 2 public
      + 6 charts CRUD + 5 chart SSE + recompute + /api/quota) → ✅
- [x] **Alembic 双向干净** (Plan 2/3 migrations 0001 + 0002 unchanged) → ✅
- [x] **chart SSE 路由 owner 校验** (跨用户 / 软删 / 不存在 统一 404) → ✅
- [x] **cache 命中 replay 零 LLM 调用** — `test_verdicts_cache_hit_replays` 中 boom
      fixture 保证 → ✅
- [x] **force + cache 存在扣 `<kind>_regen` 配额** — `test_verdicts_force_cache_charges_regen_quota` → ✅
- [x] **force + 无 cache 首次生成不扣配额** — `test_verdicts_force_no_cache_generates_without_quota` → ✅
- [x] **regen 配额超限 → 429 前置** — `test_verdicts_force_regen_quota_exceeded_429` → ✅
- [x] **LLM 双失败 → SSE error event + cache 未写** — `test_verdicts_llm_error_sse_error_no_cache` → ✅
- [x] **fallback 激活发 model event** — `test_verdicts_fallback_takes_over_on_primary_error` → ✅
- [x] **recompute 清 chart_cache + 更新 engine_version + 不扣配额** → ✅
- [x] **chips 无 cache / 无 quota / FAST_MODEL** → ✅
- [x] **GET /api/quota 未登录 401 / 登录返 7 kinds** → ✅
- [x] **server/pyproject.toml 声明 openai>=1.40 + paipan workspace dep** → ✅
- [x] **Plan 2/3/4 现有 256 测试全部不回归** (`git diff main..HEAD -- server/app/auth/ server/app/api/auth.py server/app/api/sessions.py server/app/services/auth.py server/app/services/sms.py` 零修改) → ✅

## Route Inventory

| Method | Path | Auth | Plan |
|---|---|---|---|
| GET | `/api/health` | public | Plan 2 |
| GET | `/api/config` | public | Plan 4 |
| GET | `/api/cities` | public | Plan 4 |
| POST | `/api/auth/sms/send` | public | Plan 3 |
| POST | `/api/auth/register` | public | Plan 3 |
| POST | `/api/auth/login` | public | Plan 3 |
| POST | `/api/auth/logout` | user | Plan 3 |
| GET | `/api/auth/me` | user | Plan 3 |
| DELETE | `/api/auth/account` | user | Plan 3 |
| GET | `/api/auth/sessions` | user | Plan 3 |
| DELETE | `/api/auth/sessions/{id}` | user | Plan 3 |
| GET | `/api/charts` | user | Plan 4 |
| POST | `/api/charts` | user | Plan 4 |
| GET | `/api/charts/{id}` | user | Plan 4 |
| PATCH | `/api/charts/{id}` | user | Plan 4 |
| DELETE | `/api/charts/{id}` | user | Plan 4 |
| POST | `/api/charts/{id}/restore` | user | Plan 4 |
| POST | `/api/charts/{id}/recompute` | user | **Plan 5** |
| POST | `/api/charts/{id}/verdicts` | user SSE | **Plan 5** |
| POST | `/api/charts/{id}/sections` | user SSE | **Plan 5** |
| POST | `/api/charts/{id}/dayun/{index}` | user SSE | **Plan 5** |
| POST | `/api/charts/{id}/liunian` | user SSE | **Plan 5** |
| POST | `/api/charts/{id}/chips` | user SSE | **Plan 5** |
| GET | `/api/quota` | user | **Plan 5** |

## Handoff to Plan 6

以下 Plan 5 契约稳定，Plan 6（conversation 对话层）可复用：

- `app.llm.client.{chat_stream_with_fallback, chat_with_fallback, UpstreamLLMError}`
- `app.llm.events.{sse_pack, replay_cached}`
- `app.llm.logs.insert_llm_usage_log`
- `app.retrieval.service.retrieve_for_chart`
- `app.prompts.loader / context / anchor` (shared infra)
- `app.services.quota.get_snapshot`
- `app.schemas.quota.QuotaResponse`

Plan 6 新增 `app/prompts/router.py` / `expert.py` / `chat.py` / `gua.py` 同目录追加。

## Known non-blocking items

1. `POST /api/charts/:id/import`（localStorage 迁移）未实现 —— 单独短 plan。
2. 软删 30 天硬删 cron/worker 未实现 —— Plan 7 部署期。
3. `paipan.compute` 同步跑 —— C 阶段压测后再优化。
4. ~~`LLM_STREAM_FIRST_DELTA_MS` 默认 0 —— Plan 7 监控 P50 定值。~~ **Wire 已接通**（Plan 5 cleanup Task 1）：`chart_llm` + `chart_chips` 现传 `first_delta_timeout_ms=settings.llm_stream_first_delta_ms`。env 默认 0（禁用）仍然有效，Plan 7 改 env 即可生效。
5. `llm_usage_logs` 同步写 ~20ms —— B 阶段若影响响应时序再改。
6. chips 错误发 error event vs MVP 静默返空 —— Plan 7 前端侧处理。
7. ~~`auth/deps.py:62` DEK contextvar `.set()` 无 `.reset()` —— 后续独立小 plan。~~ **已修**（Plan 5 cleanup Task 3）：`current_user` + `optional_user` 改成 yield-dep pattern，`finally` 块 `_current_dek.reset(token)`。
8. POST `/api/charts` 无 rate limit —— Plan 7 部署期 WAF/Nginx。
9. chips 无 history 上下文 —— Plan 6 补。
10. ~~`services/sms.py::send_sms_code` 未扣 `sms_send` 配额~~ —— **已修**（Plan 5 cleanup Task 2）：`send_sms_code` 现接受 `user: User | None = None` 参数，user 提供时扣 `sms_send` 配额；registration 路径 user=None 跳过扣减（user 行尚不存在）。

11. Cache-before-commit race condition —— **已修**（Plan 5 cleanup Task 4）：`stream_chart_llm` 现 commit-before-done，race 时发 `error` 代替 `done` + `error`；cache 在 commit 成功后才写。

12. chips 无 rate limit + 每调用写 `llm_usage_logs` —— 留待 **Plan 7 部署期** Nginx/WAF `limit_req` 层处理。应用层不加逻辑。

## Sign-off

Plan 5 在 Plan 2+3+4 之上执行；Plan 5 cleanup 清掉 4 个 Important follow-ups（#1 timeout wire、#3 commit-before-done、#4 sms_send quota、#5 DEK contextvar reset）+ opus reviewer Important #1 DEK leak window fix。**309 测试全绿** · 覆盖率 ≥85% · CI < 60s · wheel 可装可跑。
Plan 6 可在此基础上加 conversation 对话层。


## Plan 6 — Conversation Layer (added)

**State**: Plan 6 merged on top of Plan 2+3+4+5. No schema changes
(Conversation/Message tables already existed from Plan 4 migration 0002).

### Hard Gates

- [x] **All tests parallel-green**: `uv run --package server pytest -n auto`
      — Result: 423 passed → ✅
- [x] **Source coverage ≥ 85%** — Result: 86% → ✅
- [x] **Parallel CI wall time < 60s** — Wall time: 20.85s → ✅
- [x] **Wheel installs + boots**: `uv build --package server`; gua64.json
      packaged (`len(GUA64) == 64`) → ✅
- [x] **Alembic clean** — no new migration; existing 0001+0002 unchanged → ✅
- [x] **9 contract assertions covered**: cross-user 404 (test_conversations_ownership);
      soft-delete 404 + 410 outside 30d (test_conversations_soft_delete);
      chat_message 429 + race-on-commit (test_chat_sse_quota);
      gua 429 (test_gua_sse_quota); divination redirect (test_chat_sse_divination);
      bypass consume cta (test_chat_sse_divination); chat LLM error keeps user
      (test_chat_sse_llm_error); gua LLM error writes nothing (test_services_conversation_gua);
      chips ?conversation_id loads history (test_chips_history) → ✅

### New Route Inventory

| Method | Path | Auth | Plan |
|---|---|---|---|
| GET | `/api/charts/{chart_id}/conversations` | user | **Plan 6** |
| POST | `/api/charts/{chart_id}/conversations` | user | **Plan 6** |
| GET | `/api/conversations/{conv_id}` | user | **Plan 6** |
| PATCH | `/api/conversations/{conv_id}` | user | **Plan 6** |
| DELETE | `/api/conversations/{conv_id}` | user | **Plan 6** |
| POST | `/api/conversations/{conv_id}/restore` | user | **Plan 6** |
| GET | `/api/conversations/{conv_id}/messages` | user | **Plan 6** |
| POST | `/api/conversations/{conv_id}/messages` | user SSE | **Plan 6** |
| POST | `/api/conversations/{conv_id}/gua` | user SSE | **Plan 6** |

`POST /api/charts/{chart_id}/chips` — Plan 5 route extended in Plan 6
to accept `?conversation_id=<uuid>` for history injection.

### Plan-spec deviations (intentional)

These deviated from `docs/superpowers/specs/2026-04-18-conversation-layer-design.md`
during implementation. Each has rationale captured in the commit history:

- **`pick_chart_slice` dropped FORCE/GUARDS filtering** (Task 4 fix) — the
  Python paipan engine output is FLAT (no top-level FORCE/GUARDS arrays
  to filter), unlike the JS UI shape the original spec assumed. Slice now
  only narrows `dayun` for `timing` intent; passes through for others.
- **`chart_id` added to `ConversationDetail` schema** (Task 9 fix) — the
  SSE endpoints needed it to resolve the chart in 2 queries instead of 3.
- **`done` SSE event includes `tokens_used`** (Task 7 fix) — sibling
  parity with `chart_llm.py`.
- **`check_quota("gua")` not `"gua_cast"`** (Task 9 fix) — the original
  plan typo would have KeyError'd on every gua request.
- **Two-router split in `api/conversations.py`** (Task 9) — chart-scoped
  + conv-scoped routers improve OpenAPI grouping vs the plan's single-router.

### Handoff to Plan 7

Plan 7 (deploy / admin / guest) inherits these stable contracts:

- `app.services.conversation.{list_conversations, create_conversation, get_conversation, patch_label, soft_delete, restore}`
- `app.services.message.{insert, paginate, recent_chat_history, delete_last_cta}`
- `app.services.chat_router.classify`
- `app.services.conversation_chat.stream_message`
- `app.services.conversation_gua.stream_gua`
- `app.services.gua_cast.cast_gua` (pure function; requires Asia/Shanghai timestamp)
- `app.prompts.{router, expert, gua}`
- `app.api.conversations.router` + `charts_router`

Plan 7 surfaces:
- physical delete cron for `conversations.deleted_at` past 30d (parity
  with chart soft-delete cron)
- admin route to list conversation counts per user (no content access)
- optional `conversation_id` + `message_id` columns on `llm_usage_logs`
  for fine-grained audit
- `last_user_message` snippet in `ConversationDetail` for switcher preview UX

### Known non-blocking items (Plan 6)

13. `lib/chatHistory.js` no longer used by the new Chat.jsx — left in
    place to avoid touching tangentially related tests; safe to delete in
    Plan 7 cleanup.
14. ConversationSwitcher preview text shows empty string (server doesn't
    return `last_user_message` snippet). Plan 7 may add it.
15. Chat retry button (Chat.jsx) re-POSTs the same message — server
    accepts duplicates by design. Plan 7 may add a `regenerate` endpoint
    to delete the failed assistant + re-stream without duplicating user.
16. `pushChat` kept as alias for `appendMessage` to minimize Chat.jsx
    churn. Plan 7 cleanup: rename callsites + drop the alias.
17. Concurrent gua "起一卦" double-click race — both POSTs may DELETE the
    same cta (second is a no-op). Benign; both still INSERT gua. Race
    documented in spec §11.
18. `conversations.position` not protected by UNIQUE constraint —
    concurrent POSTs to /api/charts/:cid/conversations could compute the
    same next_pos. Plan 7 may add `UNIQUE(chart_id, position) WHERE
    deleted_at IS NULL` if observed in practice.
