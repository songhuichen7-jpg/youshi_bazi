"""Admin-protected metrics endpoint for K-factor / analytics monitoring."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import Integer, case, cast, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.core.config as _config
from app.core.db import get_db
from app.models.event import Event
from app.models.quota import LlmUsageLog

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def _require_admin(x_admin_token: Optional[str] = Header(default=None)) -> None:
    if not _config.settings.admin_token or x_admin_token != _config.settings.admin_token:
        raise HTTPException(status_code=401, detail="invalid admin token")


def _apply_window(stmt, from_: Optional[datetime], to: Optional[datetime]):
    if from_:
        stmt = stmt.where(Event.created_at >= from_)
    if to:
        stmt = stmt.where(Event.created_at < to)
    return stmt


def _apply_llm_window(stmt, from_: Optional[datetime], to: Optional[datetime]):
    if from_:
        stmt = stmt.where(LlmUsageLog.created_at >= from_)
    if to:
        stmt = stmt.where(LlmUsageLog.created_at < to)
    return stmt


def _rate(numerator: int, denominator: int) -> float:
    return (numerator / denominator) if denominator else 0.0


def _bounded_rate(numerator: int, denominator: int) -> float:
    return min(1.0, _rate(numerator, denominator))


def _event_dict(row: Event) -> dict:
    return {
        "id": row.id,
        "event": row.event,
        "anonymous_id": row.anonymous_id,
        "session_id": row.session_id,
        "user_id": str(row.user_id) if row.user_id else None,
        "type_id": row.type_id,
        "channel": row.channel,
        "from": row.from_param,
        "share_slug": row.share_slug,
        "viewport": row.viewport,
        "extra": row.extra or {},
        "created_at": row.created_at.isoformat(),
    }


def _token_total(row) -> int:
    return int((row.prompt_tokens or 0) + (row.completion_tokens or 0))


def _event_extra_int(key: str):
    return cast(Event.extra[key].astext, Integer)


def _event_extra_text(key: str):
    return Event.extra[key].astext


def _funnel_steps(counts: dict[str, int]) -> list[dict]:
    raw_steps = [
        ("visit", "访问", counts.get("page_view", 0) + counts.get("card_view", 0)),
        ("form_start", "开始填写", counts.get("form_start", 0)),
        ("form_submit", "提交表单", counts.get("form_submit", 0)),
        ("chart_success", "命盘成功", counts.get("chart_create_success", 0)),
        ("chat_send", "发送消息", counts.get("chat_send", 0)),
        ("card_share", "分享卡片", counts.get("card_share", 0)),
        ("hepan_complete", "完成合盘", counts.get("hepan_complete", 0)),
    ]
    base = raw_steps[0][2] or 0
    previous = base
    steps = []
    for key, label, count in raw_steps:
        step_rate = _bounded_rate(count, previous)
        steps.append({
            "key": key,
            "label": label,
            "count": int(count or 0),
            "rate": _bounded_rate(count, base),
            "step_rate": step_rate,
            "dropoff_rate": max(0.0, 1.0 - step_rate) if previous else 0.0,
        })
        previous = count
    return steps


@router.get("/metrics", dependencies=[Depends(_require_admin)])
async def get_metrics(
    from_: Optional[datetime] = Query(default=None),
    to: Optional[datetime] = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = select(Event.event, func.count()).group_by(Event.event)
    if from_:
        stmt = stmt.where(Event.created_at >= from_)
    if to:
        stmt = stmt.where(Event.created_at < to)
    rows = (await db.execute(stmt)).all()
    counts = {event: int(n) for event, n in rows}

    views = counts.get("card_view", 0)
    shares = counts.get("card_share", 0)
    submits = counts.get("form_submit", 0)

    return {
        "counts": counts,
        "share_rate": (shares / views) if views else 0.0,
        "form_submit_rate": (submits / views) if views else 0.0,
    }


@router.get("/overview", dependencies=[Depends(_require_admin)])
async def get_overview(
    from_: Optional[datetime] = Query(default=None),
    to: Optional[datetime] = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    count_stmt = _apply_window(
        select(Event.event, func.count()).group_by(Event.event),
        from_,
        to,
    )
    count_rows = (await db.execute(count_stmt)).all()
    counts = {event: int(n) for event, n in count_rows}

    totals_stmt = _apply_window(
        select(
            func.count(Event.id),
            func.count(func.distinct(Event.anonymous_id)),
            func.count(func.distinct(Event.session_id)),
            func.count(func.distinct(Event.user_id)),
        ),
        from_,
        to,
    )
    total_events, anonymous_visitors, sessions, identified_users = (await db.execute(totals_stmt)).one()

    recent_stmt = _apply_window(
        select(Event).order_by(desc(Event.created_at), desc(Event.id)).limit(20),
        from_,
        to,
    )
    recent = (await db.execute(recent_stmt)).scalars().all()

    page_views = counts.get("page_view", 0) + counts.get("card_view", 0)
    form_starts = counts.get("form_start", 0)
    form_submits = counts.get("form_submit", 0)
    chart_success = counts.get("chart_create_success", 0)
    card_shares = counts.get("card_share", 0)
    hepan_views = counts.get("hepan_view", 0)
    hepan_complete = counts.get("hepan_complete", 0)
    chat_sends = counts.get("chat_send", 0)
    chat_errors = counts.get("chat_error", 0)

    return {
        "totals": {
            "events": int(total_events or 0),
            "anonymous_visitors": int(anonymous_visitors or 0),
            "sessions": int(sessions or 0),
            "identified_users": int(identified_users or 0),
        },
        "counts": counts,
        "rates": {
            "visit_to_form_start": _rate(form_starts, page_views),
            "visit_to_form_submit": _rate(form_submits, page_views),
            "visit_to_chart": _rate(chart_success, page_views),
            "chart_to_share": _rate(card_shares, chart_success),
            "hepan_completion": _rate(hepan_complete, hepan_views),
            "chat_error": _rate(chat_errors, chat_sends),
        },
        "recent_events": [_event_dict(row) for row in recent],
    }


@router.get("/operations", dependencies=[Depends(_require_admin)])
async def get_operations(
    from_: Optional[datetime] = Query(default=None),
    to: Optional[datetime] = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    usage_summary_stmt = _apply_llm_window(
        select(
            func.count(LlmUsageLog.id),
            func.coalesce(func.sum(LlmUsageLog.prompt_tokens), 0),
            func.coalesce(func.sum(LlmUsageLog.completion_tokens), 0),
            func.coalesce(func.avg(LlmUsageLog.duration_ms), 0),
            func.percentile_cont(0.95).within_group(LlmUsageLog.duration_ms),
            func.count(case((LlmUsageLog.error.is_not(None), 1))),
            func.count(func.distinct(LlmUsageLog.user_id)),
        ),
        from_,
        to,
    )
    (
        calls,
        prompt_tokens,
        completion_tokens,
        avg_duration_ms,
        p95_duration_ms,
        error_count,
        active_users,
    ) = (await db.execute(usage_summary_stmt)).one()

    total_tokens = int((prompt_tokens or 0) + (completion_tokens or 0))
    calls = int(calls or 0)
    active_users = int(active_users or 0)
    error_count = int(error_count or 0)

    series_stmt = _apply_llm_window(
        select(
            func.date_trunc("day", LlmUsageLog.created_at).label("bucket"),
            func.count(LlmUsageLog.id).label("calls"),
            func.coalesce(func.sum(LlmUsageLog.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(LlmUsageLog.completion_tokens), 0).label("completion_tokens"),
            func.count(case((LlmUsageLog.error.is_not(None), 1))).label("errors"),
        )
        .group_by("bucket")
        .order_by("bucket"),
        from_,
        to,
    )
    series_rows = (await db.execute(series_stmt)).all()

    endpoint_stmt = _apply_llm_window(
        select(
            LlmUsageLog.endpoint,
            func.count(LlmUsageLog.id).label("calls"),
            func.coalesce(func.sum(LlmUsageLog.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(LlmUsageLog.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.avg(LlmUsageLog.duration_ms), 0).label("avg_duration_ms"),
            func.count(case((LlmUsageLog.error.is_not(None), 1))).label("error_count"),
        )
        .group_by(LlmUsageLog.endpoint)
        .order_by(desc(func.sum(LlmUsageLog.prompt_tokens + LlmUsageLog.completion_tokens)))
        .limit(12),
        from_,
        to,
    )
    endpoint_rows = (await db.execute(endpoint_stmt)).all()

    model_stmt = _apply_llm_window(
        select(
            LlmUsageLog.model,
            func.count(LlmUsageLog.id).label("calls"),
            func.coalesce(func.sum(LlmUsageLog.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(LlmUsageLog.completion_tokens), 0).label("completion_tokens"),
            func.count(case((LlmUsageLog.error.is_not(None), 1))).label("error_count"),
        )
        .group_by(LlmUsageLog.model)
        .order_by(desc(func.sum(LlmUsageLog.prompt_tokens + LlmUsageLog.completion_tokens)))
        .limit(8),
        from_,
        to,
    )
    model_rows = (await db.execute(model_stmt)).all()

    top_users_stmt = _apply_llm_window(
        select(
            LlmUsageLog.user_id,
            func.count(LlmUsageLog.id).label("calls"),
            func.coalesce(func.sum(LlmUsageLog.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(LlmUsageLog.completion_tokens), 0).label("completion_tokens"),
            func.count(case((LlmUsageLog.error.is_not(None), 1))).label("error_count"),
        )
        .where(LlmUsageLog.user_id.is_not(None))
        .group_by(LlmUsageLog.user_id)
        .order_by(desc(func.sum(LlmUsageLog.prompt_tokens + LlmUsageLog.completion_tokens)))
        .limit(20),
        from_,
        to,
    )
    top_user_rows = (await db.execute(top_users_stmt)).all()

    count_stmt = _apply_window(
        select(Event.event, func.count()).group_by(Event.event),
        from_,
        to,
    )
    count_rows = (await db.execute(count_stmt)).all()
    counts = {event: int(n) for event, n in count_rows}

    load_ms = _event_extra_int("load_ms")
    ttfb_ms = _event_extra_int("ttfb_ms")
    transfer_size = _event_extra_int("transfer_size")
    resource_count = _event_extra_int("resource_count")
    route = _event_extra_text("route")
    perf_where = Event.event == "page_performance"

    performance_stmt = _apply_window(
        select(
            func.count(Event.id),
            func.coalesce(func.avg(load_ms), 0),
            func.percentile_cont(0.95).within_group(load_ms),
            func.coalesce(func.avg(ttfb_ms), 0),
            func.coalesce(func.sum(transfer_size), 0),
            func.coalesce(func.avg(transfer_size), 0),
            func.coalesce(func.avg(resource_count), 0),
        ).where(perf_where),
        from_,
        to,
    )
    (
        perf_samples,
        avg_load_ms,
        p95_load_ms,
        avg_ttfb_ms,
        total_transfer_bytes,
        avg_transfer_bytes,
        avg_resource_count,
    ) = (await db.execute(performance_stmt)).one()

    performance_series_stmt = _apply_window(
        select(
            func.date_trunc("day", Event.created_at).label("bucket"),
            func.count(Event.id).label("samples"),
            func.coalesce(func.avg(load_ms), 0).label("avg_load_ms"),
            func.percentile_cont(0.95).within_group(load_ms).label("p95_load_ms"),
            func.coalesce(func.sum(transfer_size), 0).label("transfer_size"),
        )
        .where(perf_where)
        .group_by("bucket")
        .order_by("bucket"),
        from_,
        to,
    )
    performance_series_rows = (await db.execute(performance_series_stmt)).all()

    route_performance_stmt = _apply_window(
        select(
            route.label("route"),
            func.count(Event.id).label("samples"),
            func.coalesce(func.avg(load_ms), 0).label("avg_load_ms"),
            func.percentile_cont(0.95).within_group(load_ms).label("p95_load_ms"),
            func.coalesce(func.avg(ttfb_ms), 0).label("avg_ttfb_ms"),
            func.coalesce(func.sum(transfer_size), 0).label("transfer_size"),
            func.coalesce(func.avg(resource_count), 0).label("avg_resource_count"),
        )
        .where(perf_where)
        .group_by(route)
        .order_by(desc(func.percentile_cont(0.95).within_group(load_ms)))
        .limit(12),
        from_,
        to,
    )
    route_performance_rows = (await db.execute(route_performance_stmt)).all()

    return {
        "tokens": {
            "total": total_tokens,
            "prompt": int(prompt_tokens or 0),
            "completion": int(completion_tokens or 0),
            "calls": calls,
            "active_users": active_users,
            "avg_per_call": _rate(total_tokens, calls),
            "avg_per_active_user": _rate(total_tokens, active_users),
            "avg_duration_ms": float(avg_duration_ms or 0),
            "p95_duration_ms": int(p95_duration_ms or 0),
            "error_count": error_count,
            "error_rate": _rate(error_count, calls),
        },
        "series": [
            {
                "bucket": row.bucket.date().isoformat() if row.bucket else None,
                "calls": int(row.calls or 0),
                "tokens": _token_total(row),
                "prompt_tokens": int(row.prompt_tokens or 0),
                "completion_tokens": int(row.completion_tokens or 0),
                "errors": int(row.errors or 0),
            }
            for row in series_rows
        ],
        "endpoint_breakdown": [
            {
                "endpoint": row.endpoint,
                "calls": int(row.calls or 0),
                "tokens": _token_total(row),
                "prompt_tokens": int(row.prompt_tokens or 0),
                "completion_tokens": int(row.completion_tokens or 0),
                "avg_tokens": _rate(_token_total(row), int(row.calls or 0)),
                "avg_duration_ms": float(row.avg_duration_ms or 0),
                "error_count": int(row.error_count or 0),
            }
            for row in endpoint_rows
        ],
        "model_breakdown": [
            {
                "model": row.model or "unknown",
                "calls": int(row.calls or 0),
                "tokens": _token_total(row),
                "prompt_tokens": int(row.prompt_tokens or 0),
                "completion_tokens": int(row.completion_tokens or 0),
                "error_count": int(row.error_count or 0),
            }
            for row in model_rows
        ],
        "top_users": [
            {
                "user_id": str(row.user_id),
                "calls": int(row.calls or 0),
                "tokens": _token_total(row),
                "avg_tokens": _rate(_token_total(row), int(row.calls or 0)),
                "error_count": int(row.error_count or 0),
            }
            for row in top_user_rows
        ],
        "funnel": _funnel_steps(counts),
        "performance": {
            "samples": int(perf_samples or 0),
            "avg_load_ms": float(avg_load_ms or 0),
            "p95_load_ms": int(p95_load_ms or 0),
            "avg_ttfb_ms": float(avg_ttfb_ms or 0),
            "total_transfer_kb": int((total_transfer_bytes or 0) / 1024),
            "avg_transfer_kb": float((avg_transfer_bytes or 0) / 1024),
            "avg_resource_count": float(avg_resource_count or 0),
        },
        "performance_series": [
            {
                "bucket": row.bucket.date().isoformat() if row.bucket else None,
                "samples": int(row.samples or 0),
                "avg_load_ms": float(row.avg_load_ms or 0),
                "p95_load_ms": int(row.p95_load_ms or 0),
                "total_transfer_kb": int((row.transfer_size or 0) / 1024),
            }
            for row in performance_series_rows
        ],
        "route_performance": [
            {
                "route": row.route or "unknown",
                "samples": int(row.samples or 0),
                "avg_load_ms": float(row.avg_load_ms or 0),
                "p95_load_ms": int(row.p95_load_ms or 0),
                "avg_ttfb_ms": float(row.avg_ttfb_ms or 0),
                "total_transfer_kb": int((row.transfer_size or 0) / 1024),
                "avg_resource_count": float(row.avg_resource_count or 0),
            }
            for row in route_performance_rows
        ],
    }


@router.get("/events", dependencies=[Depends(_require_admin)])
async def list_events(
    event: Optional[str] = Query(default=None),
    anonymous_id: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
    from_: Optional[datetime] = Query(default=None),
    to: Optional[datetime] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = select(Event).order_by(desc(Event.created_at), desc(Event.id)).limit(limit)
    stmt = _apply_window(stmt, from_, to)
    if event:
        stmt = stmt.where(Event.event == event)
    if anonymous_id:
        stmt = stmt.where(Event.anonymous_id == anonymous_id)
    if session_id:
        stmt = stmt.where(Event.session_id == session_id)
    rows = (await db.execute(stmt)).scalars().all()
    return {"items": [_event_dict(row) for row in rows]}


@router.get("/visitors", dependencies=[Depends(_require_admin)])
async def list_visitors(
    anonymous_id: Optional[str] = Query(default=None),
    from_: Optional[datetime] = Query(default=None),
    to: Optional[datetime] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict:
    chart_count = func.sum(case((Event.event == "chart_create_success", 1), else_=0))
    share_count = func.sum(case((Event.event == "card_share", 1), else_=0))
    hepan_count = func.sum(case((Event.event == "hepan_complete", 1), else_=0))
    chat_count = func.sum(case((Event.event == "chat_send", 1), else_=0))
    error_count = func.sum(case((Event.event.in_(["chat_error", "chart_create_failed", "report_generate_failed"]), 1), else_=0))

    stmt = (
        select(
            Event.anonymous_id,
            func.count(Event.id).label("event_count"),
            func.count(func.distinct(Event.session_id)).label("session_count"),
            func.min(Event.created_at).label("first_seen_at"),
            func.max(Event.created_at).label("last_seen_at"),
            chart_count.label("chart_count"),
            share_count.label("share_count"),
            hepan_count.label("hepan_count"),
            chat_count.label("chat_count"),
            error_count.label("error_count"),
            func.max(Event.type_id).label("last_type_id"),
        )
        .where(Event.anonymous_id.is_not(None))
        .group_by(Event.anonymous_id)
        .order_by(desc(func.max(Event.created_at)))
        .limit(limit)
    )
    stmt = _apply_window(stmt, from_, to)
    if anonymous_id:
        stmt = stmt.where(Event.anonymous_id == anonymous_id)

    rows = (await db.execute(stmt)).all()
    return {
        "items": [
            {
                "anonymous_id": row.anonymous_id,
                "event_count": int(row.event_count or 0),
                "session_count": int(row.session_count or 0),
                "first_seen_at": row.first_seen_at.isoformat() if row.first_seen_at else None,
                "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
                "chart_count": int(row.chart_count or 0),
                "share_count": int(row.share_count or 0),
                "hepan_count": int(row.hepan_count or 0),
                "chat_count": int(row.chat_count or 0),
                "error_count": int(row.error_count or 0),
                "last_type_id": row.last_type_id,
            }
            for row in rows
        ],
    }
