# server

FastAPI backend for bazi-analysis. Provides the HTTP/DB/encryption
foundation used by downstream plans (auth, charts, LLM).

> **Note:** this package is being built up task-by-task per Plan 2. Some
> commands below (alembic, uvicorn) depend on files that land in later
> tasks (Task 6 bootstraps alembic, Task 2 ships `app/main.py`). See
> `docs/superpowers/plans/2026-04-17-backend-foundation.md`.

## Dev quickstart

    # from repo root
    cp server/.env.example server/.env
    # edit .env: set DATABASE_URL and ENCRYPTION_KEK
    uv sync --package server --extra dev

    # run migrations (alembic config lands in Task 6)
    uv run --package server alembic -c server/alembic.ini upgrade head

    # run tests (testcontainers will start its own Postgres)
    uv run --package server pytest server/tests/

    # run the app locally
    uv run --package server uvicorn app.main:app --reload
