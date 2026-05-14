# Relationship shard

> ⚠️ 脱敏版本。完整 shard 内容为项目核心 IP。

感情 / 婚恋 / 配偶宫；性别先行（女命官杀为夫星，男命财星为妻星）；不默认异性婚配。

加载方式：runtime 由 `server/app/prompts/loader.py` 通过 `@lru_cache` 读取，按 router 输出的 intent 条件拼装到 expert prompt 中。

完整版可面试时演示。设计思路见 [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §5。
