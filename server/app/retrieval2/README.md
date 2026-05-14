# retrieval2 — claim 级古籍检索

替代 `app.retrieval`（v1）的检索层。**部署优先**：

- 零新依赖，纯 Python
- 索引产物 ~12 MB，运行内存 ~50 MB
- 域内 API 唯一（DeepSeek），无境外依赖

## 架构

```
                 离线（一次性）
classics/*.md
   ↓ splitter            零依赖
ClaimUnit (4962 条，~150 字 / 条)
   ↓ tagger.tag_all      DeepSeek API（一次成本 ~¥10）
ClaimTags
   ↓ bm25.build_bm25     纯 Python
   ↓ kg.build_kg         纯 Python（内存）
artifacts/
   claims.jsonl  (~3 MB)
   tags.jsonl    (~2 MB)
   bm25.pkl      (~10 MB)
   manifest.json

                 运行时（每次 chat）
chart + kind + user_msg
   ↓ intents.bazi_chart_to_intents
   ↓ BM25 + KG → top 30 候选     ← 30 ms 内
   ↓ selector.select             DeepSeek-fast 一次调用 ~500 ms-1 s
top 6 短断语 → list[V1Hit]
```

## 文件

| 模块 | 职责 |
|---|---|
| `types.py` | `ClaimUnit` / `ClaimTags` / `QueryIntent` / `RetrievalHit` 数据契约 + 版本号 |
| `normalize.py` + `data/synonyms.json` | 异体字归一 + 同义词扩展（不改代码，直接改 JSON） |
| `splitter.py` | md → ClaimUnit；段落感知；稳定 ID |
| `tokenizer.py` | 字 1+2 gram + 同义词注入 |
| `bm25.py` | 纯 Python BM25 倒排（pickle 落盘） |
| `kg.py` | tag 反向索引（启动时从 tags.jsonl 在内存重建） |
| `tagger.py` | DeepSeek 离线打标 + 受控词表 |
| `intents.py` | 命盘 → 查询意图（领域知识收敛在这） |
| `selector.py` | DeepSeek 当 selector，从 30 候选挑 6 条 |
| `service.py` | 与 v1 同签名 `retrieve_for_chart` |
| `storage.py` | JSONL/manifest IO |

## 跑 indexer

```bash
# 第一次：split + 打标 + bm25（需 DEEPSEEK_API_KEY，~5 分钟，~¥10）
PYTHONPATH=server python -m scripts.build_classics_index --rebuild

# 不打标快速 split + bm25（CI / 烟测用，无网络）
PYTHONPATH=server python -m scripts.build_classics_index --no-tag --rebuild

# 增量：只处理变化文件
PYTHONPATH=server python -m scripts.build_classics_index

# 时间窗口（每次最多打标 N 条；适合长批分轮跑）
PYTHONPATH=server python -m scripts.build_classics_index --max-tag 500
```

## 接入生产

调用方已切到 retrieval2（`server/app/services/{chart_llm,conversation_chat}.py`、
`server/app/api/charts.py`），无 feature flag。

环境变量（可选）：
- `RETRIEVAL2_INDEX_ROOT` 自定义 artifact 目录（默认 `server/var/retrieval2/`）

部署清单：
- 把 `server/app/retrieval2/` 代码部署进去
- 把 `server/var/retrieval2/{claims,tags}.jsonl + bm25.pkl` 拷过去（一次性 ~12 MB）
- 服务器需要 `DEEPSEEK_API_KEY`（chat 服务本来就用）

## 降级路径

| 场景 | service 行为 |
|---|---|
| 索引文件缺失 | 返回 `[]`，调用方 fallback 到 v1（feature flag 控制） |
| Selector LLM 调用失败 | 自动 fallback 到 BM25+KG 融合分前 K |
| 测试需要确定性 | `use_selector=False` 跳过 LLM，直接返回融合分前 K |

## 扩展点

**加一本新古籍**
1. md 放到 `classics/<key>/*.md`
2. 在 `data/synonyms.json` 的 `book_labels` 加一行
3. 在 `splitter._PROFILES` 里登记 `BookProfile`（可选；默认配置一般够用）
4. 跑 indexer

**加一种新标签维度**（如 神煞 细分）
1. `tagger.VOCAB` 加新词表 + prompt 字段说明
2. `types.ClaimTags` 加新字段（默认空 tuple）
3. `kg.KG_FIELDS` 加新字段
4. 改 `TAGGER_PROMPT_VERSION` → 强制重打标

**加新意图类型**（如 "夫妻流年合冲"）
1. `intents.bazi_chart_to_intents` 加一条 `_emit(...)` 调用
2. 不改任何检索内核

**换 selector 模型**
1. `selector._call_deepseek` 内部换调用即可——接口 (messages → text) 不变

## 与 v1 对比

| 维度 | v1 现状 | retrieval2 |
|---|---|---|
| 检索原子 | 整章 dump | 单 claim (50-200 字) |
| 给 LLM 的字数 / case | ~10 K-20 K | ~600-1500 |
| 同义词处理 | 硬编码 if-else | 数据文件 |
| 加新书 | 改 5+ 张路由表 | 跑 indexer |
| 索引磁盘 | 0（运行时读 md） | ~12 MB |
| 索引内存 | 0 | ~50 MB |
| Runtime LLM 调用 | 0-2 次（plan+filter） | 0-1 次（selector） |
| 代码 | 2217 行 | ~1100 行 |
