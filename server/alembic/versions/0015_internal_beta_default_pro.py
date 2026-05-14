"""Internal beta: 把存量 lite / free 用户一次性升级到 pro。

Revision ID: 0015_internal_beta_default_pro
Revises: 0014_hepan_messages
Create Date: 2026-05-03 21:00:00

内测期把所有还在 lite 档的用户(包括内测前注册过的、guest_token 复活回来的)
一次性升到 pro,让他们体验不被配额卡住。新建用户的 default 在应用层
(services/auth.py) 已经写成 plan='pro',这条 migration 是给存量数据的。

为什么不改 server_default:
  改了 DB-level default 会影响测试夹具(很多 test 假设 plan='lite')。
  保留 DB default='lite',应用层显式设 'pro' 双套参数;付费上线时去掉
  应用层的覆盖,行为就回到 lite 默认,不需要再写一条 migration。

只升级当前 plan_expires_at IS NULL (没付过费) 的 lite/free 用户;
真付费用户的档位不动。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0015_internal_beta_default_pro"
down_revision: Union[str, Sequence[str], None] = "0014_hepan_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 注意:plan_expires_at IS NULL 是判断"没真付费"的标记 —
    # standard / pro 真付费用户都会被 service 写一个到期时间。
    op.execute("""
        UPDATE users
           SET plan = 'pro'
         WHERE plan IN ('lite', 'free')
           AND plan_expires_at IS NULL
    """)


def downgrade() -> None:
    # 回滚:把没付费的 pro 用户回到 lite。已付费 (plan_expires_at IS NOT NULL)
    # 的不动。注意:这只能恢复"档位 = pro 且没付费"的行 — 内测期可能也有人
    # 真付费,但回滚时分不出来。所以这条 downgrade 是"最小破坏"版本,实际
    # 上付费上线场景不该回滚。
    op.execute("""
        UPDATE users
           SET plan = 'lite'
         WHERE plan = 'pro'
           AND plan_expires_at IS NULL
    """)
