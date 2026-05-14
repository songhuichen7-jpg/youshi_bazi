"""Alembic environment — async mode, reads URL from app.core.config.settings."""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import models so Base.metadata is populated.
from app.models import Base
from app.core.config import settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject URL from settings at runtime if the caller hasn't already provided one
# (e.g. tests set it via cfg.set_main_option before invoking command.upgrade).
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", str(settings.database_url))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
