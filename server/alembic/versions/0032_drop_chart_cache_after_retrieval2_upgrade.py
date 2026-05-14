"""drop section / verdicts / dayun_step / liunian chart_cache after
retrieval2 upgrade (chunk_type axis + tagger v2 + 命理师 review 8 项).

Cache rationale: chart_llm_service replays cached LLM output verbatim
when ``cache_row and not force``. Existing cached panels were written
against the pre-upgrade retrieval (single-key fast tagger + old policy
routing + no chunk_type weighting + missing 男/女命/health/主十神
generalisations + missing 破格/日支冲合/流派分歧 intents). Without a
forced refresh, users keep seeing the old output even after the new
index lands.

Strategy: delete every cached row that goes through retrieval (section,
verdicts, dayun_step, liunian). Next visit re-runs retrieval + LLM with
the new pipeline. ``classics`` cache is versioned separately via
CLASSICS_CACHE_VERSION and not touched here — bump that constant if
you also want the 古书定调 panel re-polished.

Cost: one LLM regeneration per (chart, panel) on next view. Charts
that were never visited after a panel cache wrote stay un-impacted.
This is the same pattern as 0031 (classics v11→v12 drop).
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op


revision: str = "0032_section_cache_drop"
down_revision: Union[str, Sequence[str], None] = "0031_classics_v11_drop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM chart_cache "
        "WHERE kind IN ('section', 'verdicts', 'dayun_step', 'liunian')"
    )


def downgrade() -> None:
    pass
