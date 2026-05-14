"""Chart CRUD service.

Layer boundaries:
- In:  (AsyncSession, User, Pydantic request)
- Out: ORM Chart row (or list thereof)
- Errors: raise typed ServiceError subclasses; api/ maps to HTTP.

DEK contextvar is assumed already set by the current_user dep at route
entry — service code never touches it explicitly.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import column, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.quotas import chart_max_for
from app.models.chart import Chart, ChartCache
from app.models.user import User
from app.schemas.chart import CacheSlot, ChartCreateRequest
from app.services import paipan_adapter
from app.services.exceptions import ChartAlreadyDeleted, ChartLimitExceeded, ChartNotFound


SOFT_DELETE_WINDOW = timedelta(days=30)


async def create_chart(
    db: AsyncSession,
    user: User,
    req: ChartCreateRequest,
) -> tuple[Chart, list[str]]:
    """Create a new chart for ``user``.

    Pipeline:
      1. Normalize city (write canonical name back to birth_input if resolved).
      2. Run paipan.compute → (paipan_dict, warnings, engine_version).
      3. INSERT chart; flush to get row.
      4. Post-check active-count ≤ MAX_CHARTS_PER_USER; over-limit raises
         ChartLimitExceeded (caller's transaction rolls back).
    """
    # NOTE: spec §3.2 step 1 — canonicalize before persisting.
    birth = req.birth_input.model_copy()
    if birth.city:
        resolved = paipan_adapter.resolve_city(birth.city)
        if resolved is not None:
            birth = birth.model_copy(update={"city": resolved["canonical"]})

    # NOTE: spec §3.1 — paipan call; ValueError → InvalidBirthInput (400).
    paipan_dict, warnings, engine_version = paipan_adapter.run_paipan(birth)

    chart = Chart(
        user_id=user.id,
        label=req.label,
        birth_input=birth.model_dump(),  # EncryptedJSONB transparent
        paipan=paipan_dict,
        engine_version=engine_version,
    )
    db.add(chart)
    await db.flush()  # obtain chart.id + verify schema constraints

    # NOTE: spec §2.4 — post-check 命盘上限（按 user.plan 查 chart_max_for）；
    # 软删的不计。post-check 而不是 pre-check 是为了让 race-condition 落点
    # 在 INSERT 后；db.flush 后我们只是回滚事务，不会留半生成的 chart 行。
    active_count = (await db.execute(
        select(func.count(Chart.id)).where(
            Chart.user_id == user.id,
            Chart.deleted_at.is_(None),
        )
    )).scalar_one()
    chart_cap = chart_max_for(user.plan)
    if active_count > chart_cap:
        raise ChartLimitExceeded(limit=chart_cap)

    return chart, warnings


async def list_charts(db: AsyncSession, user: User) -> list[Chart]:
    """Active charts for ``user``, newest first.

    Secondary sort on ctid DESC breaks ties when created_at stamps are identical
    (e.g. multiple inserts within the same PostgreSQL transaction where now() is
    transaction-stable); ctid is assigned monotonically per insert so it
    reliably reflects insertion order within a page.
    """
    rows = (await db.execute(
        select(Chart).where(
            Chart.user_id == user.id,
            Chart.deleted_at.is_(None),
        ).order_by(Chart.created_at.desc(), column("ctid").desc())
    )).scalars().all()
    return list(rows)


async def get_chart(
    db: AsyncSession,
    user: User,
    chart_id: UUID,
    *,
    include_soft_deleted: bool = False,
) -> Chart:
    """Owner-scoped lookup. Raises ChartNotFound for any miss.

    include_soft_deleted=False (default): WHERE deleted_at IS NULL.
    include_soft_deleted=True: allow soft-deleted rows within 30d window;
        rows deleted_at <= now() - 30d still raise ChartNotFound (out-of-window).
    """
    stmt = select(Chart).where(
        Chart.id == chart_id,
        Chart.user_id == user.id,
    )
    if not include_soft_deleted:
        stmt = stmt.where(Chart.deleted_at.is_(None))
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise ChartNotFound()

    if include_soft_deleted and row.deleted_at is not None:
        # Window check using DB clock to match deleted_at timezone semantics.
        # NOTE: spec §0.3 decision #5 — 30d window; beyond this → 404.
        cutoff = (await db.execute(
            text("SELECT now() - INTERVAL '30 days'")
        )).scalar_one()
        if row.deleted_at <= cutoff:
            raise ChartNotFound()

    return row


async def get_cache_slots(db: AsyncSession, chart_id: UUID) -> list[CacheSlot]:
    """Return all chart_cache rows as CacheSlot schema objects.

    Plan 4: chart_cache table is never written; this function returns [].
    Plan 5 LLM routes write cache → function returns non-empty automatically.
    """
    rows = (await db.execute(
        select(ChartCache).where(ChartCache.chart_id == chart_id)
    )).scalars().all()
    return [
        CacheSlot(
            kind=r.kind,
            key=r.key,
            has_cache=r.content is not None,
            model_used=r.model_used,
            regen_count=r.regen_count,
            generated_at=r.generated_at,
        )
        for r in rows
    ]


async def update_label(
    db: AsyncSession,
    user: User,
    chart_id: UUID,
    label: str | None,
) -> Chart:
    """Update chart.label for an active (non-soft-deleted) chart."""
    chart = await get_chart(db, user, chart_id)  # raises ChartNotFound
    chart.label = label
    chart.updated_at = datetime.now(tz=timezone.utc)
    await db.flush()
    return chart


async def soft_delete(db: AsyncSession, user: User, chart_id: UUID) -> None:
    """Set chart.deleted_at = now(). Raises ChartAlreadyDeleted if already soft-deleted."""
    chart = await get_chart(db, user, chart_id, include_soft_deleted=True)
    if chart.deleted_at is not None:
        raise ChartAlreadyDeleted()
    chart.deleted_at = datetime.now(tz=timezone.utc)
    await db.flush()


async def restore(db: AsyncSession, user: User, chart_id: UUID) -> Chart:
    """Clear chart.deleted_at for a soft-deleted chart still within 30d window.

    Raises:
      ChartNotFound — not exist / wrong owner / not soft-deleted / past 30d window
      ChartLimitExceeded — restoring would push active count over the user's
        plan-specific 命盘上限（chart_max_for(user.plan)）
    """
    chart = await get_chart(db, user, chart_id, include_soft_deleted=True)
    if chart.deleted_at is None:
        # Not in soft-deleted state; same 404 response as "not exist" (防枚举).
        raise ChartNotFound()

    # Post-check active count WITHOUT counting this row (still soft-deleted).
    active_count = (await db.execute(
        select(func.count(Chart.id)).where(
            Chart.user_id == user.id,
            Chart.deleted_at.is_(None),
        )
    )).scalar_one()
    chart_cap = chart_max_for(user.plan)
    if active_count >= chart_cap:
        raise ChartLimitExceeded(limit=chart_cap)

    chart.deleted_at = None
    chart.updated_at = datetime.now(tz=timezone.utc)
    await db.flush()
    return chart


async def recompute(db: AsyncSession, user: User, chart_id: UUID) -> tuple[Chart, list[str]]:
    """Re-run paipan for chart and clear all chart_cache entries.

    Does NOT trigger LLM. Does NOT charge quota. Soft-deleted charts raise
    ChartNotFound via get_chart's default include_soft_deleted=False.
    """
    chart = await get_chart(db, user, chart_id)    # soft-deleted → ChartNotFound

    from app.schemas.chart import BirthInput
    birth = BirthInput(**chart.birth_input)
    paipan_dict, warnings, engine_version = paipan_adapter.run_paipan(birth)

    chart.paipan = paipan_dict
    chart.engine_version = engine_version
    chart.updated_at = datetime.now(tz=timezone.utc)
    await db.flush()

    await db.execute(
        text("DELETE FROM chart_cache WHERE chart_id = :cid"),
        {"cid": chart.id},
    )
    return chart, warnings
