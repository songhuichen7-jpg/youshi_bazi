"""SQLAlchemy async engine + session factory.

Engine is created lazily via ``create_engine_from_settings()`` so tests can
build a separate engine pointed at their testcontainers Postgres URL without
fighting a module-level singleton.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import anyio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine_from_settings(url: str | None = None, **kwargs: Any) -> AsyncEngine:
    """Create an AsyncEngine.

    Args:
        url: overrides ``settings.database_url`` (used by tests).
        **kwargs: merged into engine kwargs.

    pool 默认 5 + 10 (单 worker dev 友好);生产多 worker 部署应该按
    "(同时活跃 SSE 数 + 留 spare 给短 API)/worker 数" 估算,典型 prod
    值 pool_size=20 + max_overflow=30 = 50 总连接 / worker。设环境变量
    DB_POOL_SIZE / DB_MAX_OVERFLOW 即可调整,不用改代码。
    """
    from app.core.config import settings

    defaults = {
        "pool_pre_ping": True,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        # idle 连接闲置 30 分钟回收 — 防止 PG 那边 idle_in_transaction
        # 或者 cloud PG 5-15 分钟自动断开导致下次拿到失效连接。
        "pool_recycle": 1800,
    }
    defaults.update(kwargs)
    return create_async_engine(url or str(settings.database_url), **defaults)


# Module-level singleton for production use (Plan 3+ routes). Tests build
# their own engine and don't touch this.
_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def _ensure_engine() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_maker
    if _session_maker is None:
        _engine = create_engine_from_settings()
        _session_maker = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_maker


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields an AsyncSession that commits on success
    and rolls back on exception."""
    maker = _ensure_engine()
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            with anyio.CancelScope(shield=True):
                await session.rollback()
            raise


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Public hook for non-FastAPI consumers (cron loops, CLI scripts).

    使用模式：
        async with get_session_maker()() as db:
            await do_work(db)
            await db.commit()
    Caller 自己决定 commit/rollback — get_db 自动 commit 那套不要再套一遍。
    """
    return _ensure_engine()


async def dispose_engine() -> None:
    """Called from FastAPI lifespan shutdown."""
    global _engine, _session_maker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_maker = None
