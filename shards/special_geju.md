# Special geju shard

> ⚠️ 脱敏版本。完整 shard 内容为项目核心 IP。

特殊格局成立条件硬核校验；古籍要求缺一项即不成立，绝不凑话。

加载方式：runtime 由 `server/app/prompts/loader.py` 通过 `@lru_cache` 读取，按 router 输出的 intent 条件拼装到 expert prompt 中。

完整版可面试时演示。设计思路见 [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §5。
