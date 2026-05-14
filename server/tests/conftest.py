"""Test fixtures. Sets env vars at module top BEFORE importing any app module.

conftest.py is imported by pytest before any test file, so any env setup here
happens before app.core.config.settings instantiates.
"""
from __future__ import annotations

import os

# Set test env BEFORE any `from app...` import anywhere in the test tree.
os.environ.setdefault("ENV", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("ENCRYPTION_KEK", "00" * 32)  # all-zero test key
# Real database_url gets monkeypatched by postgres_container fixture below.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://placeholder:placeholder@localhost:1/placeholder")

# Now safe to import.
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from testcontainers.postgres import PostgresContainer


@pytest.fixture(autouse=True)
def _restore_config_after_reloads():
    """Some tests monkeypatch ENCRYPTION_KEK and ``importlib.reload(app.core.config)``
    to exercise startup validation. That leaves ``app.core.config.settings`` stuck
    on the test value in ``sys.modules``, which pollutes any later test that reads
    the singleton. This autouse fixture reloads config + main back to the
    baseline ``"00"*32`` KEK after each test.
    """
    yield
    import importlib
    import sys

    os.environ["ENCRYPTION_KEK"] = "00" * 32
    cfg = sys.modules.get("app.core.config")
    if cfg is not None:
        importlib.reload(cfg)
    main_mod = sys.modules.get("app.main")
    if main_mod is not None:
        importlib.reload(main_mod)


@pytest.fixture(scope="session")
def postgres_container():
    """One Postgres 16 container for the whole test session."""
    # NOTE: alpine keeps startup < 5s on most hosts.
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def database_url(postgres_container) -> str:
    """asyncpg-flavored URL for tests that need to connect."""
    raw = postgres_container.get_connection_url()
    # testcontainers may return postgresql:// or postgresql+psycopg2://; normalise.
    if raw.startswith("postgresql+psycopg2://"):
        return "postgresql+asyncpg://" + raw[len("postgresql+psycopg2://"):]
    if raw.startswith("postgresql://"):
        return "postgresql+asyncpg://" + raw[len("postgresql://"):]
    return raw


@pytest.fixture(scope="session", autouse=True)
def apply_migrations(database_url):
    """Ensure the schema is in place before ANY test that touches the DB runs.

    Critical under pytest-xdist: each worker has its own session, so without
    this autouse fixture test_models (which just assumes tables exist) can run
    before test_migrations (which explicitly upgrades), and the insert fails
    with 'relation users does not exist'. Running upgrade once per worker
    session is cheap (<1s on warm cache).
    """
    from alembic import command
    from alembic.config import Config

    # alembic env.py uses async_engine_from_config; pass the asyncpg URL directly.
    cfg = Config("server/alembic.ini")
    cfg.set_main_option("script_location", "server/alembic")
    cfg.set_main_option("sqlalchemy.url", str(database_url))
    command.upgrade(cfg, "head")
    yield


@pytest_asyncio.fixture
async def async_client() -> AsyncIterator[AsyncClient]:
    """httpx AsyncClient bound to the FastAPI app via ASGI — no uvicorn."""
    from app.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # lifespan is NOT triggered by ASGITransport alone; we need to run it.
        async with app.router.lifespan_context(app):
            yield client
