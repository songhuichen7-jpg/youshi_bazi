"""跨进程锁 (Redis-backed) + in-memory fallback,统一接口。

用法:

    from app.core.distributed_lock import named_lock, LockBusyError

    async with named_lock("conv:abc123", ttl=120):
        ...  # 跨 worker 互斥,同时也是 in-memory 锁的语义

    # 想知道锁在不在被占用而不是排队等:
    if await is_locked("conv:abc123"):
        raise LockBusyError(...)

设计要点:
  - Redis 可用 → SET NX EX,SETNX 失败立即抛 LockBusyError(我们语义是
    "拒绝并发",不是 "排队等",跟原来 asyncio.Lock 用 .locked() 检查的
    用法等价)。释放时 Lua 脚本检查 token 防误删。
  - Redis 不可用 → asyncio.Lock + 模块级 dict + LRU cap,行为跟原来
    完全一致。
  - TTL 必填 — Redis 锁必须有过期时间,避免 worker 崩溃锁泄露。

cleanup:
  - in-memory dict 用 OrderedDict + max_keys cap (默认 4096) 防止永久膨
    胀;到上限按 LRU 淘汰。生产场景每个 conv/hepan 一个 key,4k 够用。
  - Redis key TTL 由调用方传入,典型 60-180s(SSE 流的最长合理时长)。
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from collections import OrderedDict
from contextlib import asynccontextmanager

from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)


class LockBusyError(Exception):
    """锁已被占用 — 调用方按"拒绝并发"语义处理。"""


# Lua 脚本: 释放锁时检查 token 跟 SET 时一致才删,避免 A 设的锁过期
# 后 B 拿到同名锁,A 的 finally 把 B 的锁删掉。
_RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


# In-memory fallback ─────────────────────────────────────────────────
_MAX_INMEMORY_LOCKS = 4096
_inmem_locks: "OrderedDict[str, asyncio.Lock]" = OrderedDict()


def _inmem_get(name: str) -> asyncio.Lock:
    lock = _inmem_locks.get(name)
    if lock is None:
        lock = asyncio.Lock()
        _inmem_locks[name] = lock
        # LRU cap: 超 cap 就淘汰最早一条,但只淘汰未持有的(持有的留给业务跑完)
        while len(_inmem_locks) > _MAX_INMEMORY_LOCKS:
            oldest_name, oldest_lock = next(iter(_inmem_locks.items()))
            if oldest_lock.locked():
                # 持有中,不能扔 — 跳过它继续找下一个空闲的
                # 极端场景下所有都持有就会 break,接受少量超额(最多 +N 持有中的)
                _inmem_locks.move_to_end(oldest_name)
                # 再看一眼最早的,如果还是 locked 就停,避免死循环
                if next(iter(_inmem_locks.items()))[1].locked():
                    break
                continue
            _inmem_locks.popitem(last=False)
    else:
        # LRU touch
        _inmem_locks.move_to_end(name)
    return lock


# Public API ─────────────────────────────────────────────────────────

@asynccontextmanager
async def named_lock(name: str, *, ttl: int = 120):
    """互斥语义 — 已被占用立即抛 LockBusyError,不排队等。

    Args:
        name: 锁的逻辑名,业务自定义命名空间 (e.g. "conv:abc", "hepan:xyz")
        ttl:  Redis 锁过期时间(秒)。in-memory 模式下 ttl 不参与。
    """
    redis_client = get_redis()
    if redis_client is not None:
        token = secrets.token_hex(16)
        rkey = f"lock:{name}"
        try:
            ok = await redis_client.set(rkey, token, nx=True, ex=ttl)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis lock acquire failed for %s, falling back: %r", name, exc)
            ok = False
            redis_client = None  # 走 fallback 分支
        if redis_client is not None:
            if not ok:
                raise LockBusyError(name)
            try:
                yield
            finally:
                try:
                    await redis_client.eval(_RELEASE_LUA, 1, rkey, token)
                except Exception as exc:  # noqa: BLE001
                    # 释放失败不致命 — TTL 兜底,锁会在 ttl 秒后自动消失
                    logger.warning("Redis lock release failed for %s: %r", name, exc)
            return

    # in-memory fallback
    lock = _inmem_get(name)
    if lock.locked():
        raise LockBusyError(name)
    async with lock:
        yield


async def is_locked(name: str) -> bool:
    """非阻塞探测 — 用在"想立即拒绝并发"的代码路径头部。

    Redis 模式下 EXISTS 探测;不存在或异常都返 False (允许进入,后续
    named_lock acquire 时再做权威判断,避免误报阻塞用户)。
    """
    redis_client = get_redis()
    if redis_client is not None:
        try:
            return bool(await redis_client.exists(f"lock:{name}"))
        except Exception:  # noqa: BLE001
            return False
    lock = _inmem_locks.get(name)
    return bool(lock and lock.locked())


# tests 用
def _reset_for_tests() -> None:
    _inmem_locks.clear()
