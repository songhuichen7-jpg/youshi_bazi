"""Fix hepan_invites.reading_text — should be BYTEA, not TEXT.

Revision ID: 0012_hepan_reading_text_bytea
Revises: 0011_hepan_user_id_uuid
Create Date: 2026-05-02 00:00:00

0011 把 reading_text 写成了 sa.Text（Postgres TEXT），但 EncryptedText
的 ``impl = LargeBinary``（BYTEA）。SA 写入时把密文 bytes 强塞进 TEXT
列，PG 用某种编码留下来；读出时 AESGCM.decrypt 拿到 str 当 nonce 直接
TypeError。所以这条 reading 的 cache 实际不能用，写一次就坏。

修法：alter to BYTEA。中间会丢已存的 reading_text（5 行测试数据，无所谓）—
把列里 NULL 化再切类型，比 USING cast 干净。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0012_hepan_reading_text_bytea"
down_revision: Union[str, Sequence[str], None] = "0011_hepan_user_id_uuid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 老 reading_text 全是脏数据（写法错的密文）— 清掉再切类型
    op.execute("UPDATE hepan_invites SET reading_text = NULL")
    op.execute(
        "ALTER TABLE hepan_invites "
        "ALTER COLUMN reading_text TYPE BYTEA USING NULL"
    )


def downgrade() -> None:
    op.execute("UPDATE hepan_invites SET reading_text = NULL")
    op.execute(
        "ALTER TABLE hepan_invites "
        "ALTER COLUMN reading_text TYPE TEXT USING NULL"
    )
