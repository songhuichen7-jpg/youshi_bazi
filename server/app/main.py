"""FastAPI entry point — foundation layer.

GET /api/health exposes basic process status plus a small LLM capability hint
used by the frontend during bootstrap.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.billing import admin_router as billing_admin_router
from app.api.billing import router as billing_router
from app.api.card import router as card_router
from app.api.hepan import router as hepan_router
from app.api.charts import router as charts_router
from app.api.media import router as media_router
from app.api.conversations import charts_router as conversations_charts_router
from app.api.conversations import router as conversations_router
from app.api.quota import router as quota_router
from app.api.sessions import router as sessions_router
from app.api.public import router as public_router
from app.api.tracking import router as tracking_router
from app.api.wx import router as wx_router
from app.core.config import settings
from app.core.logging import setup_logging


async def _subscription_expire_loop() -> None:
    """每 ``settings.subscription_expire_loop_seconds`` 秒扫一次到期订阅。

    每轮新开一个 db session（避免长 session 持着连接）；任何异常都吞掉
    继续 loop — 这是 best-effort，挂了不该把进程也带死。loop 取消时
    asyncio.CancelledError 会自然冒到 lifespan 的 wait，正常退出。
    """
    interval = settings.subscription_expire_loop_seconds
    if interval <= 0:
        return
    log = logging.getLogger("billing.expire")
    # 进程刚启动时先睡一轮再做 — 避免冷启 thundering-herd
    while True:
        try:
            await asyncio.sleep(interval)
            from app.core.db import get_session_maker
            from app.services.subscription import expire_due
            async with get_session_maker()() as db:
                count = await expire_due(db)
                if count:
                    await db.commit()
                    log.info("expired %d subscriptions", count)
        except asyncio.CancelledError:
            raise
        except Exception:                # noqa: BLE001
            log.exception("subscription expire loop iteration failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level)

    # KEK is loaded inside lifespan so tests that don't need it (e.g. health
    # smoke) can override via monkeypatch before import.
    from app.core.crypto import load_kek
    app.state.kek = load_kek()

    from app.services.card.loader import load_all
    load_all()
    from app.services.hepan.loader import load_all as load_hepan_all
    load_hepan_all()

    expire_task = asyncio.create_task(
        _subscription_expire_loop(), name="subscription-expire-loop",
    )

    try:
        yield
    finally:
        expire_task.cancel()
        try:
            await expire_task
        except asyncio.CancelledError:
            pass
        from app.core.db import dispose_engine
        await dispose_engine()


app = FastAPI(
    title="bazi-analysis backend",
    version=settings.version,
    lifespan=lifespan,
    docs_url="/api/docs" if settings.env == "dev" else None,
    redoc_url=None,
)

# ── CORS ──────────────────────────────────────────────────────────────
# 同源部署（nginx 反代前后端到同一 origin）→ settings.cors_origins 留空
# 不挂 middleware，省一份开销 + 减少调试时的"为什么 OPTIONS 也走 ASGI"
# 困扰。跨域部署填 cors_origins 逗号分隔列表。
if settings.cors_origins:
    _origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if _origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=_origins,
            allow_credentials=True,   # cookie auth 需要
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
            expose_headers=["Retry-After"],
        )

# ── 全局 API rate-limit（in-memory 滑动窗口） ────────────────────────
# 优先级 < CORS（middleware 添加顺序倒过来生效），意思是 CORS 先匹配，
# 然后到 rate-limit。避免预检 OPTIONS 直接撞 429。
if settings.rate_limit_enabled:
    from app.core.rate_limit import RateLimitMiddleware
    app.add_middleware(
        RateLimitMiddleware,
        limit_per_minute=settings.rate_limit_per_minute,
    )

_CARDS_DATA_DIR = Path(__file__).parent / "data" / "cards"
app.mount(
    "/static/cards",
    StaticFiles(directory=str(_CARDS_DATA_DIR)),
    name="card_static",
)
_HEPAN_ILLUSTRATIONS_DIR = Path(__file__).parent / "data" / "hepan" / "illustrations"
app.mount(
    "/static/hepan/illustrations",
    StaticFiles(directory=str(_HEPAN_ILLUSTRATIONS_DIR)),
    name="hepan_illustration_static",
)
_MEDIA_CACHE_DIR = Path(__file__).resolve().parents[1] / "var" / "media-cache"
_MEDIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/static/media-cache",
    StaticFiles(directory=str(_MEDIA_CACHE_DIR)),
    name="media_cache_static",
)

_AVATAR_DIR = Path(__file__).resolve().parents[1] / "var" / "avatars"
_AVATAR_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/static/avatars",
    StaticFiles(directory=str(_AVATAR_DIR)),
    name="avatar_static",
)

app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(billing_admin_router)
app.include_router(card_router)
app.include_router(hepan_router)
app.include_router(sessions_router)
app.include_router(charts_router)
app.include_router(media_router)
app.include_router(conversations_charts_router)
app.include_router(conversations_router)
app.include_router(quota_router)
app.include_router(public_router)
app.include_router(tracking_router)
app.include_router(wx_router)


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "version": settings.version,
        "env": settings.env,
        "llm": {
            "hasKey": bool(settings.llm_api_key),
            "model": settings.llm_model,
        },
    }
