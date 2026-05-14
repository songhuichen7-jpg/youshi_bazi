"""Seed cases for router eval.

每条 case 包括:
- message: 用户输入
- history: 上文 (按从旧到新),作为 router context
- expected_primary: 期望的 primary intent
- expected_secondary: 期望的 secondary_intents 集合 (集合比较,顺序不重要)
- difficulty: easy / medium / hard / adversarial / followup
- failure_pattern: 已知失败模式标签,用于诊断聚合

注: expected_secondary 是 "**至少**应该包含" 的集合 — router 多产几项不算错,
但漏产任何一项都算召回失败。这避免对 router "稳妥多召回" 的策略过度惩罚。
"""

# History helper: 用户/助手交替的简短上下文
def _h(*pairs: tuple[str, str]) -> list[dict]:
    out = []
    for u, a in pairs:
        out.append({"role": "user", "content": u})
        out.append({"role": "assistant", "content": a})
    return out


SEEDS: list[dict] = [
    # ── EASY: 单一 intent 强 keyword,期望 secondary 为空 ────────────────────
    {"message": "我感情怎么样", "history": [],
     "expected_primary": "relationship", "expected_secondary": [],
     "difficulty": "easy"},
    {"message": "我事业怎么样", "history": [],
     "expected_primary": "career", "expected_secondary": [],
     "difficulty": "easy"},
    {"message": "我财运如何", "history": [],
     "expected_primary": "wealth", "expected_secondary": [],
     "difficulty": "easy"},
    {"message": "我身体好不好", "history": [],
     "expected_primary": "health", "expected_secondary": [],
     "difficulty": "easy"},
    {"message": "我长什么样", "history": [],
     "expected_primary": "appearance", "expected_secondary": [],
     "difficulty": "easy"},
    {"message": "什么是七杀格", "history": [],
     "expected_primary": "meta", "expected_secondary": [],
     "difficulty": "easy"},
    {"message": "你好", "history": [],
     "expected_primary": "chitchat", "expected_secondary": [],
     "difficulty": "easy"},
    {"message": "用一首歌形容我", "history": [],
     "expected_primary": "media", "expected_secondary": [],
     "difficulty": "easy"},
    {"message": "我应不应该跳槽", "history": [],
     "expected_primary": "divination", "expected_secondary": [],
     "difficulty": "easy"},
    {"message": "我是不是从格", "history": [],
     "expected_primary": "special_geju", "expected_secondary": [],
     "difficulty": "easy"},
    {"message": "我什么时候结婚", "history": [],
     "expected_primary": "timing", "expected_secondary": [],
     "difficulty": "easy"},
    {"message": "我性格怎么样", "history": [],
     "expected_primary": "personality", "expected_secondary": [],
     "difficulty": "easy"},

    # 表达多样化,同一 intent 不同 phrasing
    {"message": "我能赚到钱吗", "history": [],
     "expected_primary": "wealth", "expected_secondary": [],
     "difficulty": "easy"},
    {"message": "什么时候能升职", "history": [],
     "expected_primary": "career", "expected_secondary": ["timing"],
     "difficulty": "easy"},
    {"message": "我和我对象合不合适", "history": [],
     "expected_primary": "relationship", "expected_secondary": [],
     "difficulty": "easy"},

    # ── MEDIUM: 跨轴问题,期望 secondary 非空 ──────────────────────────────
    {"message": "事业和感情都讲讲", "history": [],
     "expected_primary": "career", "expected_secondary": ["relationship"],
     "difficulty": "medium"},
    {"message": "我适合做什么工作,能赚钱吗", "history": [],
     "expected_primary": "career", "expected_secondary": ["wealth"],
     "difficulty": "medium"},
    {"message": "我健康和性格", "history": [],
     "expected_primary": "health", "expected_secondary": ["personality"],
     "difficulty": "medium"},
    {"message": "我大运怎么样,性格会变吗", "history": [],
     "expected_primary": "timing", "expected_secondary": ["personality"],
     "difficulty": "medium"},
    {"message": "我未来事业会怎样", "history": [],
     "expected_primary": "career", "expected_secondary": ["timing"],
     "difficulty": "medium"},
    {"message": "我以后会过得好吗", "history": [],
     "expected_primary": "timing", "expected_secondary": ["meta"],
     "difficulty": "medium"},
    {"message": "我以后能富贵吗", "history": [],
     "expected_primary": "wealth", "expected_secondary": ["timing", "meta"],
     "difficulty": "medium"},
    {"message": "我老婆怎么样,我们关系", "history": [],
     "expected_primary": "relationship", "expected_secondary": ["appearance"],
     "difficulty": "medium"},

    # ── HARD: "整体/底色/核心结构" 类总览问法 ─────────────────────────────
    # 这些是 2026-05-09 router 重写的目标 case,过去会被分到 personality
    {"message": "介绍一下我的整体", "history": [],
     "expected_primary": "meta", "expected_secondary": ["personality"],
     "difficulty": "hard", "failure_pattern": "overall_to_meta_personality"},
    {"message": "我命的底色是什么", "history": [],
     "expected_primary": "meta", "expected_secondary": ["personality"],
     "difficulty": "hard", "failure_pattern": "overall_to_meta_personality"},
    {"message": "讲一下我这盘", "history": [],
     "expected_primary": "meta", "expected_secondary": ["personality"],
     "difficulty": "hard", "failure_pattern": "overall_to_meta_personality"},
    {"message": "我整体看看,性格和命运", "history": [],
     "expected_primary": "meta", "expected_secondary": ["personality"],
     "difficulty": "hard", "failure_pattern": "overall_to_meta_personality"},
    {"message": "我命好不好", "history": [],
     "expected_primary": "meta", "expected_secondary": ["personality"],
     "difficulty": "hard", "failure_pattern": "overall_to_meta_personality"},
    {"message": "总论一下我的命盘", "history": [],
     "expected_primary": "meta", "expected_secondary": ["personality"],
     "difficulty": "hard"},
    {"message": "我有没有大富大贵", "history": [],
     "expected_primary": "wealth", "expected_secondary": ["meta"],
     "difficulty": "hard", "failure_pattern": "fortune_grade"},
    {"message": "我是不是贵命", "history": [],
     "expected_primary": "meta", "expected_secondary": ["wealth"],
     "difficulty": "hard", "failure_pattern": "fortune_grade"},
    {"message": "我这盘的核心矛盾", "history": [],
     "expected_primary": "meta", "expected_secondary": ["personality"],
     "difficulty": "hard"},
    {"message": "我的核心结构", "history": [],
     "expected_primary": "meta", "expected_secondary": ["personality"],
     "difficulty": "hard"},

    # ── ADVERSARIAL: keyword 陷阱 ─────────────────────────────────────────
    # 桃花 + 时间词 — relationship 优先 (router 有显式规则)
    {"message": "我桃花运今年怎么样", "history": [],
     "expected_primary": "relationship", "expected_secondary": ["timing"],
     "difficulty": "adversarial", "failure_pattern": "taohua_not_timing"},
    {"message": "我什么时候有桃花", "history": [],
     "expected_primary": "relationship", "expected_secondary": ["timing"],
     "difficulty": "adversarial", "failure_pattern": "taohua_not_timing"},

    # "会不会" 但实际是问命格而非起卦
    {"message": "我会不会发财", "history": [],
     "expected_primary": "wealth", "expected_secondary": [],
     "difficulty": "adversarial", "failure_pattern": "会不会_not_divination"},
    {"message": "我能不能富贵", "history": [],
     "expected_primary": "wealth", "expected_secondary": ["meta"],
     "difficulty": "adversarial"},

    # 问概念而非分析
    {"message": "正官和七杀的区别是什么", "history": [],
     "expected_primary": "meta", "expected_secondary": [],
     "difficulty": "adversarial"},
    {"message": "格局是什么", "history": [],
     "expected_primary": "meta", "expected_secondary": [],
     "difficulty": "adversarial"},

    # media 比 personality 更具体
    {"message": "用一首歌形容我这盘", "history": [],
     "expected_primary": "media", "expected_secondary": [],
     "difficulty": "adversarial", "failure_pattern": "media_priority"},
    {"message": "我像哪部电影", "history": [],
     "expected_primary": "media", "expected_secondary": [],
     "difficulty": "adversarial", "failure_pattern": "media_priority"},
    {"message": "用一种花形容我", "history": [],
     "expected_primary": "media", "expected_secondary": [],
     "difficulty": "adversarial"},

    # divination 真起卦 vs 命格判断
    {"message": "我现在该不该买这套房", "history": [],
     "expected_primary": "divination", "expected_secondary": [],
     "difficulty": "adversarial"},
    {"message": "我跟他能不能复合", "history": [],
     "expected_primary": "divination", "expected_secondary": [],
     "difficulty": "adversarial"},

    # ── FOLLOWUP: 隐式追问,需要 history 推断 ──────────────────────────────
    {"message": "那今年呢",
     "history": _h(("我事业怎么样", "你的事业格局是…")),
     "expected_primary": "timing", "expected_secondary": ["career"],
     "difficulty": "followup", "failure_pattern": "context_carry"},
    {"message": "那感情呢",
     "history": _h(("我事业怎么样", "你的事业格局是…")),
     "expected_primary": "relationship", "expected_secondary": [],
     "difficulty": "followup"},
    {"message": "再讲讲",
     "history": _h(("我整体怎么样", "你的命格是月令辛金…")),
     "expected_primary": "meta", "expected_secondary": ["personality"],
     "difficulty": "followup"},
    {"message": "那我老婆呢",
     "history": _h(("我感情怎么样", "你的正缘…")),
     "expected_primary": "relationship", "expected_secondary": [],
     "difficulty": "followup"},
    {"message": "什么意思",
     "history": _h(("我命格是什么", "你的格局是七杀格…")),
     "expected_primary": "meta", "expected_secondary": [],
     "difficulty": "followup"},

    # ── CHITCHAT 边界 ────────────────────────────────────────────────────
    {"message": "嗯", "history": [],
     "expected_primary": "chitchat", "expected_secondary": [],
     "difficulty": "easy"},
    {"message": "谢谢你", "history": [],
     "expected_primary": "chitchat", "expected_secondary": [],
     "difficulty": "easy"},
    {"message": "好的明白了",
     "history": _h(("我命格", "你是七杀格...")),
     "expected_primary": "chitchat", "expected_secondary": [],
     "difficulty": "easy"},

    # ── 含糊时间词 ───────────────────────────────────────────────────────
    {"message": "我未来会怎样", "history": [],
     "expected_primary": "timing", "expected_secondary": ["meta"],
     "difficulty": "medium", "failure_pattern": "vague_timing"},
    {"message": "我接下来几年", "history": [],
     "expected_primary": "timing", "expected_secondary": [],
     "difficulty": "medium"},
    {"message": "我以后事业会怎样", "history": [],
     "expected_primary": "career", "expected_secondary": ["timing"],
     "difficulty": "medium"},

    # ── 短追问/单字提问 ──────────────────────────────────────────────────
    {"message": "婚姻",
     "history": _h(("讲讲我", "你这个命...")),
     "expected_primary": "relationship", "expected_secondary": [],
     "difficulty": "medium"},
    {"message": "事业",
     "history": _h(("讲讲我", "你这个命...")),
     "expected_primary": "career", "expected_secondary": [],
     "difficulty": "medium"},

    # ── 多面手问题 (3+ axis,期望 router 抓住主轴 + 1-2 secondary) ────────
    {"message": "我事业感情财运都讲讲", "history": [],
     "expected_primary": "career",
     "expected_secondary": ["relationship", "wealth"],
     "difficulty": "hard"},
]


def total() -> int:
    return len(SEEDS)


__all__ = ["SEEDS", "total"]
