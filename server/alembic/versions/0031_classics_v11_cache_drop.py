"""Drop v11 classics cache rows after OCR-fold + punctuation post-process fix.

Revision ID: 0031_classics_v11_drop
Revises: 0030_classics_drop_null
Create Date: 2026-05-08

After diagnosing both empty-stuck charts (2003-08-29 / 2004-01-06):

1. **Provenance check failure on OCR-variant 湏 / 㐫 / 㸔 / 㑹 / 歳** — LLM
   "corrects" these to 须/凶/看/会/岁; zhconv didn't fold them; substring
   check fails. Fixed by extending `_OCR_FOLD_GROUPS`.

2. **Validation rejected unpunctuated quotes** — LLM at temp=0 ignores the
   "must add punctuation" rule for 三命通会 cluster-style raw text. Fixed
   by removing the rejection and adding a server-side fast-tier LLM
   punctuation pass that strips back to the same chars.

Existing v11 rows (which had to pass the old, stricter validation) may be
fine, but bumping to v12 forces the panel to re-fetch with the new logic
so previously-stuck charts unstick on next view.
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "0031_classics_v11_drop"
down_revision: Union[str, Sequence[str], None] = "0030_classics_drop_null"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM chart_cache WHERE kind = 'classics' AND key = 'v11'")


def downgrade() -> None:
    pass
