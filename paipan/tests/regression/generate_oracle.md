# 如何生成 Oracle Fixtures

Oracle = Node.js paipan-engine 的输出，作为 Python port 的"真值"。

## 一次性生成

```bash
cd /Users/veko/code/usual/bazi-analysis/paipan-engine
npm install  # 若未装
node scripts/dump-oracle.js \
  ../paipan/tests/regression/birth_inputs.json \
  ../paipan/tests/regression/fixtures/
```

## 冻结规则

Oracle 一旦生成**不再改**。如发现 Node 版 bug：
- 不修 Node 版
- 在 Python port 里也照搬这个 bug（为保证 byte-exact）
- 单独立项修"paipan 算法修正"——同时更新 Node 和 Python 版 + 重跑 oracle

Node 版将打 tag `paipan-engine-oracle-v1` 并归档到 `archive/paipan-engine/`。

## 已知 silent TODO（不要在 port 阶段 fix）

- `liLiang.js` 定义了 `keDiscount: 0.6` 但从未应用。Python port 必须同样"定义但不应用"。详见 `docs/paipan-port-inventory.md` 的 `ming/liLiang.js` 章节顶部 callout。
