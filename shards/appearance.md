# Appearance shard

> ⚠️ 脱敏版本。完整 shard 内容为项目核心 IP。

三命通会性情相貌体系；日主五行 + 主导十神 + 月令气候 → 身材肤色面相；不加现代审美词。

加载方式：runtime 由 `server/app/prompts/loader.py` 通过 `@lru_cache` 读取，按 router 输出的 intent 条件拼装到 expert prompt 中。

完整版可面试时演示。设计思路见 [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §5。
