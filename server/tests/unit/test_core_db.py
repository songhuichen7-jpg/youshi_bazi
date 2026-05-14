"""core.db dependency transaction behavior."""
from __future__ import annotations

import asyncio

import pytest

from app.core import db as db_mod


pytestmark = pytest.mark.asyncio


class _FakeSession:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def _fake_maker(session: _FakeSession):
    class _Maker:
        def __call__(self):
            return session

    return _Maker()


async def test_get_db_rolls_back_when_request_is_cancelled(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(db_mod, "_ensure_engine", lambda: _fake_maker(session))

    dependency = db_mod.get_db()
    yielded = await dependency.__anext__()
    assert yielded is session

    with pytest.raises(asyncio.CancelledError):
        await dependency.athrow(asyncio.CancelledError())

    assert session.rolled_back is True
    assert session.committed is False
