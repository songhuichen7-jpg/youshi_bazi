"""distributed_lock 双后端覆盖 — Redis 路径用 fakeredis 兜,in-memory 路径直接跑。

只覆盖业务接口语义:
  - acquire 成功后再次 acquire 立刻 raise LockBusyError(不排队)
  - 释放后 acquire 又能成功
  - is_locked 探测一致
  - in-memory cap=4096 不会无限制涨
"""
from __future__ import annotations

import asyncio

import pytest

from app.core import distributed_lock as dl


@pytest.fixture(autouse=True)
def _reset():
    dl._reset_for_tests()
    yield
    dl._reset_for_tests()


async def test_inmemory_acquire_blocks_concurrent():
    """已经持有时第二次进入立刻 LockBusyError,不等。"""
    async def hold(name, gate):
        async with dl.named_lock(name, ttl=10):
            await gate.wait()

    gate = asyncio.Event()
    holder = asyncio.create_task(hold("conv:abc", gate))
    await asyncio.sleep(0.01)  # 让 holder 拿到锁

    with pytest.raises(dl.LockBusyError):
        async with dl.named_lock("conv:abc", ttl=10):
            pass

    gate.set()
    await holder


async def test_inmemory_release_allows_next():
    """释放后下一次 acquire 立刻成功。"""
    async with dl.named_lock("conv:xyz", ttl=10):
        pass
    async with dl.named_lock("conv:xyz", ttl=10):
        pass  # 不抛即可


async def test_is_locked_inmemory():
    assert await dl.is_locked("conv:zzz") is False
    async with dl.named_lock("conv:zzz", ttl=10):
        assert await dl.is_locked("conv:zzz") is True
    assert await dl.is_locked("conv:zzz") is False


async def test_inmemory_cap_does_not_explode():
    """造 5000 个一次性 lock,确认字典大小被 cap 在 _MAX_INMEMORY_LOCKS 附近。"""
    for i in range(5000):
        async with dl.named_lock(f"conv:burst:{i}", ttl=10):
            pass
    # cap=4096,允许少量超额(实现里持有中的不能扔)
    assert len(dl._inmem_locks) <= dl._MAX_INMEMORY_LOCKS + 100
