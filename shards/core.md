# Core shard - 始终加载

> ⚠️ 脱敏版本。完整 shard 内容为项目核心 IP。

全局输出风格、引用纪律、术语 + 白话、回答长度、媒介卡（[[song:]] / [[movie:]] / [[flower:]]）规则。约 180 行。

加载方式：runtime 由 `server/app/prompts/loader.py` 通过 `@lru_cache` 读取，按 router 输出的 intent 条件拼装到 expert prompt 中。

完整版可面试时演示。设计思路见 [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §5。
