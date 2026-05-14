"""Sliding-window rate limiter for /api/ endpoints.

后端两套实现,按 settings.redis_url 自动选:
  - 有 Redis    → Redis Sorted Set 共享窗口,跨 worker 准确
  - 没 Redis    → in-memory deque,单 worker 准确,多 worker 退化为
                   N×limit (代码里早就写了这权衡)

策略:
  - GET /api/health, /api/config, /api/cities, /api/auth/me, /static/ 不限流
  - 其余 /api/ 路由共享一个全局窗口,limit_per_minute req/min/key
  - key 优先级: session cookie > X-Forwarded-For > client.host
  - 超额返 429 + Retry-After,body 跟既有 ServiceError 一致

只在 settings.rate_limit_enabled 开启时挂;test 默认关闭以免污染。
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)


# 不限流的路径(前缀匹配)— 健康检查、公共只读、auth me 心跳
_EXEMPT_PREFIXES = (
    "/api/health",
    "/api/config",
    "/api/cities",
    "/api/auth/me",        # 登录态滑窗刷新,前端会高频调(rolling session)
    "/static/",            # 静态资源
)


def _is_exempt(path: str) -> bool:
    return any(path.startswith(p) for p in _EXEMPT_PREFIXES)


class _InMemorySlidingWindow:
    """每个 key 一个 deque,存最近 window_seconds 内的请求时间戳(秒)。

    pop 老数据 O(k) 但每次最多弹到 limit 这么多,所以摊销 O(1) per request。
    单 lock 保护多请求竞争 — 内存级操作,开销极小。
    单 worker 内准确;多 worker 各自一份桶,实际上限 ~N×limit。
    """

    __slots__ = ("limit", "window_seconds", "_buckets", "_lock", "_max_keys")

    def __init__(self, limit: int, window_seconds: float = 60.0, max_keys: int = 10_000) -> None:
        self.limit = max(1, int(limit))
        self.window_seconds = float(window_seconds)
        # max_keys 防止跑很久积累过多 key 导致内存涨;到上限按 FIFO 淘汰
        # 最旧的桶。in-memory 模式下这个简单 cap 比"完全无限制"更负责。
        self._max_keys = max_keys
        self._buckets: dict[str, Deque[float]] = {}
        self._lock = asyncio.Lock()

    async def hit(self, key: str) -> tuple[bool, float]:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        async with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = deque()
                self._buckets[key] = bucket
                # 简单 cap: 超 max_keys 就丢最旧一条 (insertion order)
                if len(self._buckets) > self._max_keys:
                    old_key = next(iter(self._buckets))
                    self._buckets.pop(old_key, None)
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit:
                retry_after = self.window_seconds - (now - bucket[0])
                return False, max(retry_after, 1.0)
            bucket.append(now)
            return True, 0.0


class _RedisSlidingWindow:
    """Redis Sorted Set 实现 — 跨 worker 共享。

    每个 key 一个 ZSET,score = epoch_ms。每次 hit:
      1. ZREMRANGEBYSCORE 把 cutoff 之前的全清掉
      2. ZCARD 当前窗口内的请求数
      3. 没满就 ZADD now;满就返 false + retry_after
      4. EXPIRE 设 TTL = window+10s,让闲置 key 自动归零

    TTL 让 Redis 自己回收闲 key,不需要清理任务;计数集中在 Redis,
    多 worker 严格共享。
    """

    __slots__ = ("limit", "window_seconds", "_redis")

    def __init__(self, limit: int, redis_client, window_seconds: float = 60.0) -> None:
        self.limit = max(1, int(limit))
        self.window_seconds = float(window_seconds)
        self._redis = redis_client

    async def hit(self, key: str) -> tuple[bool, float]:
        now_ms = int(time.time() * 1000)
        cutoff_ms = now_ms - int(self.window_seconds * 1000)
        rkey = f"rl:{key}"

        # pipeline 把 4 个操作打包成一次 round-trip
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(rkey, 0, cutoff_ms)
                pipe.zcard(rkey)
                pipe.zadd(rkey, {f"{now_ms}-{id(pipe)}": now_ms})
                pipe.expire(rkey, int(self.window_seconds) + 10)
                _, count_before, _, _ = await pipe.execute()
        except Exception as exc:  # noqa: BLE001
            # Redis 抽风时降级 — 放行而非阻断,避免 503 风暴
            logger.warning("Redis rate-limit error, allowing request: %r", exc)
            return True, 0.0

        # count_before 是 ZADD 之前的计数。如果已经 >= limit,这次 ZADD
        # 已经把 N+1 加进去了,需要 ZRANGE 找最早一条算 retry,然后回滚我们刚加的。
        if count_before >= self.limit:
            try:
                # 回滚刚加的 — score range 精确匹配 now_ms
                await self._redis.zremrangebyscore(rkey, now_ms, now_ms)
                # 拿当前最早那一条的 score 算 retry_after
                earliest = await self._redis.zrange(rkey, 0, 0, withscores=True)
                if earliest:
                    earliest_ms = float(earliest[0][1])
                    retry_after = self.window_seconds - (now_ms - earliest_ms) / 1000
                    return False, max(retry_after, 1.0)
                return False, self.window_seconds
            except Exception:  # noqa: BLE001
                return False, self.window_seconds

        return True, 0.0


def _make_window(limit: int, window_seconds: float = 60.0):
    """工厂 — 按 redis 可用性选实现。"""
    redis_client = get_redis()
    if redis_client is not None:
        logger.info("rate-limit using Redis backend (limit=%d/%ds)", limit, window_seconds)
        return _RedisSlidingWindow(limit, redis_client, window_seconds)
    logger.info("rate-limit using in-memory backend (limit=%d/%ds)", limit, window_seconds)
    return _InMemorySlidingWindow(limit, window_seconds)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """挂在 main.py 的 ASGI 栈最外层。

    顺序敏感:必须在能解出 user_id 的下游(auth)之前能拿到 cookie,
    我们这里直接读 session cookie hash 作为 key,不依赖 auth dep
    (middleware 跑在 dep 之前)。未登录则用 IP。
    """

    def __init__(self, app: ASGIApp, *, limit_per_minute: int) -> None:
        super().__init__(app)
        self._window = _make_window(limit_per_minute, window_seconds=60.0)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/") or _is_exempt(path):
            return await call_next(request)
        key = self._key_for(request)
        allowed, retry_after = await self._window.hit(key)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": {
                        "code": "RATE_LIMITED",
                        "message": "请求太频繁,喘口气再试。",
                        "details": {"retry_after_seconds": int(retry_after)},
                    },
                },
                headers={"Retry-After": str(int(retry_after))},
            )
        return await call_next(request)

    @staticmethod
    def _key_for(request: Request) -> str:
        # session cookie 是 sha256 token 的前 N 字符(具体见 auth.py),不
        # 解析就拿原文当 key 即可——同一会话同一 key,足够分桶。
        cookie = request.cookies.get("session")
        if cookie:
            return f"sess:{cookie[:32]}"
        # 未登录 fallback 到 IP — 反代场景看 X-Forwarded-For 第一个 hop
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return f"ip:{xff.split(',')[0].strip()}"
        client = request.client
        return f"ip:{client.host if client else 'unknown'}"
