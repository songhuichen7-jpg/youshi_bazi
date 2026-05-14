"""Optional Redis client — async, single module-level connection pool.

设计原则:
  - settings.redis_url 留空 → get_redis() 返回 None，调用方走 in-memory fallback
  - settings.redis_url 有值 → 第一次 get_redis() 建立连接池，后续复用
  - 连接池由 redis-py 内部管理，多协程并发取连接安全
  - decode_responses=True 让 .get/.set 直接收发 str，省去到处 .decode()
  - 启动失败不让进程崩 — 记录 warning，调用方降级。生产部署 Redis 不通
    本身就是事故信号，但应用还能跑（rate-limit 退到 in-memory，锁退到
    asyncio.Lock，都比 503 强）。

为什么不放在 lifespan startup 里强制 ping:
  Redis 偶尔抽风（network blip）不应该 take down 整个 API。我们做软依
  赖处理 — 第一次 get_redis() 建立连接，后续操作失败就吞错降级。
"""
from __future__ import annotations

import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_pool: object | None = None
_attempted: bool = False


def get_redis():
    """Return a redis.asyncio.Redis client or None if Redis is not configured.

    None 是契约的一部分 — 调用方必须处理 None 走降级路径。
    第一次失败的话标记 _attempted 不重试,避免每个请求都打一次 Redis
    导致连锁慢。重置只能 restart 进程。
    """
    global _pool, _attempted
    if _pool is not None:
        return _pool
    if _attempted:
        return None
    if not settings.redis_url:
        _attempted = True
        return None
    try:
        # 延迟 import — redis 是可选 dep,没装也别拖进 import graph
        from redis.asyncio import Redis  # noqa: PLC0415
        _pool = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            # 短超时:Redis 卡住别拖死请求,降级走 in-memory 即可
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
            # 自动重连而不是抛 ConnectionError 立即失败
            retry_on_timeout=True,
        )
        logger.info("Redis client initialised (url=%s)", _redact_url(settings.redis_url))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis client init failed, falling back to in-memory: %r", exc)
        _attempted = True
        _pool = None
    return _pool


def _redact_url(url: str) -> str:
    """rediss://user:pass@host:6379 → rediss://***@host:6379 (log-safe)"""
    if "@" not in url:
        return url
    proto, rest = url.split("://", 1) if "://" in url else ("redis", url)
    _, host = rest.split("@", 1)
    return f"{proto}://***@{host}"


async def shutdown_redis() -> None:
    """Lifespan shutdown hook — close pool gracefully."""
    global _pool
    if _pool is not None:
        try:
            await _pool.aclose()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis shutdown error: %r", exc)
        _pool = None


# tests 用 — reset module state between cases
def _reset_for_tests() -> None:
    global _pool, _attempted
    _pool = None
    _attempted = False
