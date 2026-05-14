"""Lifespan: sentinel KEK must raise before yielding."""
from __future__ import annotations

import importlib

import pytest


@pytest.mark.asyncio
async def test_sentinel_kek_fails_startup(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEK", "__CHANGE_ME_64_HEX__")
    # Force fresh settings + main import so the sentinel is read.
    import app.core.config as cfg
    importlib.reload(cfg)
    import app.main as main_mod
    importlib.reload(main_mod)

    with pytest.raises(RuntimeError, match="sentinel"):
        async with main_mod.app.router.lifespan_context(main_mod.app):
            pass
