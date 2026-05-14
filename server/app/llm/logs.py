"""llm_usage_logs writer — independent session, decoupled from caller's transaction.

Why a fresh session
-------------------
This table is a write-only audit log. Earlier版本和 caller 共享 ``db`` —
INSERT 跟业务事务绑定。Stream 取消 / lock 拒绝 / commit 漏跑都会让日志一并丢失
(2026-05-10 的 Codex 跑 162 query 只落库 17 行就是这个 bug)。

修法：每次写日志开一条独立 session,执行 INSERT 立刻 commit,跟业务路径完全解耦。
代价是每次 +1 connection (从 pool 取),但日志保证落地。

异常仍然 swallow — 业务流量不能因日志故障被打断。
"""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text

from app.core.db import get_session_maker

_log = logging.getLogger(__name__)


async def insert_llm_usage_log(
    db: Any | None = None,  # 保留入参兼容老调用,内部不使用
    *,
    user_id: UUID,
    chart_id: UUID | None,
    endpoint: str,
    model: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    duration_ms: int,
    error: str | None = None,
    retrieval_claims: list[dict] | None = None,
) -> None:
    """INSERT into llm_usage_logs in its own transaction; swallow DB errors.

    ``retrieval_claims``: list of {id, source, text} dicts from the retrieval
    pipeline. Stored as JSON text for offline analysis.
    """
    claims_json: str | None = None
    if retrieval_claims:
        claims_json = json.dumps(
            [{"id": h.get("id"), "source": h.get("source"), "text": h.get("text", "")[:120]}
             for h in retrieval_claims],
            ensure_ascii=False,
        )

    sql = text("""
        INSERT INTO llm_usage_logs
            (user_id, chart_id, endpoint, model,
             prompt_tokens, completion_tokens, duration_ms,
             intent, error, retrieval_claims, created_at)
        VALUES (:uid, :cid, :ep, :mdl, :pt, :ct, :dms, NULL, :err, :rc, now())
    """)
    params = {
        "uid": user_id, "cid": chart_id, "ep": endpoint,
        "mdl": model or "",  # DB 列 NOT NULL,空串 = 未知模型
        "pt": prompt_tokens or 0, "ct": completion_tokens or 0,
        "dms": duration_ms, "err": error, "rc": claims_json,
    }

    try:
        SessionMaker = get_session_maker()
        async with SessionMaker() as log_db:
            try:
                await log_db.execute(sql, params)
                await log_db.commit()
            except Exception as e:  # noqa: BLE001
                _log.warning("llm_usage_logs insert failed: %s", e)
                # async with 退出时自动 rollback,不需要显式
    except Exception as e:  # noqa: BLE001 — 兜底:连 sessionmaker 都拿不到也不能炸 caller
        _log.warning("llm_usage_logs session open failed: %s", e)
