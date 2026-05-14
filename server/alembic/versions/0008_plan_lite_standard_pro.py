"""Membership 1.0: relax users.plan from {free,pro} to {lite,standard,pro}.

Revision ID: 0008_plan_lite_standard_pro
Revises: 0007_user_avatar
Create Date: 2026-05-01 00:00:00

Two semantic moves baked into one migration:

1. ``free`` is renamed to ``lite``. ``free`` 是 Plan 3 时代的占位，新会员体系
   下默认免费档叫 lite — 跟 standard / pro 的英文名站在同一档系上读起来
   更顺。CHECK constraint 同步换。

2. **现有用户全部升到 ``pro``，而不是回落到 lite**。这是 internal-beta 的
   有意决策：现存测试用户已经习惯了"基本无限"的额度，突然把他们卡到 lite
   的 30 条 / 天会让大家撞墙；先把他们 grandfather 到 pro，等付费链路
   接好后再挨个谈降档。新注册才 default 到 lite（server_default 同步改）。

Downgrade 把 plan 改回 free/pro 的 CHECK，把所有 lite/standard 都映射回
free，pro 维持。注意 downgrade 不还原"老 free 现在是 pro"那一步 —
真正回滚需要快照才能还原。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0008_plan_lite_standard_pro"
down_revision: Union[str, Sequence[str], None] = "0007_user_avatar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 老 'free' 行 → 'pro'（grandfather 内测用户，避免突然撞 lite 上限）
    op.execute("UPDATE users SET plan = 'pro' WHERE plan = 'free'")

    # 2. 默认值：新注册落到 lite
    op.execute("ALTER TABLE users ALTER COLUMN plan SET DEFAULT 'lite'")

    # 3. CHECK constraint：drop 老 free/pro，加 lite/standard/pro
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS plan_enum")
    op.execute(
        "ALTER TABLE users "
        "ADD CONSTRAINT plan_enum "
        "CHECK (plan IN ('lite','standard','pro'))"
    )


def downgrade() -> None:
    # 顺序很关键：必须先 DROP 现行的 plan_enum (lite/standard/pro) 约束，
    # 才能 UPDATE 把 lite/standard → free（不然 'free' 不在新枚举里立即违
    # 反约束被拒）。原版"先 UPDATE 后 DROP"在 DB 里实际没 lite 行的环境
    # 蒙混过去，但 testcontainers 跑过 register_user 之后会撞到。
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS plan_enum")
    # 把 lite / standard 都映射回 free（pro 维持）— 不可逆地丢失档位差异。
    op.execute("UPDATE users SET plan = 'free' WHERE plan IN ('lite','standard')")
    op.execute("ALTER TABLE users ALTER COLUMN plan SET DEFAULT 'free'")
    op.execute(
        "ALTER TABLE users "
        "ADD CONSTRAINT plan_enum "
        "CHECK (plan IN ('free','pro'))"
    )
