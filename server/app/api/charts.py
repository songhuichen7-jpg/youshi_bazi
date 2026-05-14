"""HTTP layer for /api/charts/*. Thin wrapper over services/chart."""
from __future__ import annotations

import asyncio
import json
from functools import partial
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import check_quota, current_user
from app.core.db import get_db
from app.models.chart import Chart, ChartCache
from app.models.user import User
from app.prompts import (
    chips as prompts_chips,
    dayun_step as prompts_dayun_step,
    liunian as prompts_liunian,
    sections as prompts_sections,
    verdicts as prompts_verdicts,
)
from app.schemas.chart import (
    BirthInput,
    CacheSlot,
    ChartClassicsResponse,
    ChartCreateRequest,
    ChartDetail,
    ChartLabelUpdateRequest,
    ChartListItem,
    ChartListResponse,
    ChartResponse,
)
from app.schemas.llm import LiunianBody, SectionBody
from app.retrieval2 import service as retrieval_service
# NOTE: retrieval2 returns claim-level (50-200 char) hits already selected
# by DeepSeek; the v1 filter_classics_for_display layer is no longer needed
# (retrieval2 does its own LLM-based selection in selector.py).
from app.services import chart as chart_service
from app.services import chart_chips as chart_chips_service
from app.services import classics_polisher
from app.services import chart_llm as chart_llm_service
from app.services import paipan_adapter
from app.services.exceptions import ServiceError

router = APIRouter(
    prefix="/api/charts",
    tags=["charts"],
    dependencies=[Depends(current_user)],
)


def _http_error(err: ServiceError) -> HTTPException:
    return HTTPException(status_code=err.status, detail=err.to_dict())


async def _chart_to_response(
    chart: Chart,
    *,
    db: AsyncSession,
    warnings: list[str] | None = None,
) -> ChartResponse:
    slots = await chart_service.get_cache_slots(db, chart.id)
    return ChartResponse(
        chart=ChartDetail(
            id=chart.id,
            label=chart.label,
            birth_input=BirthInput(**chart.birth_input),
            paipan=chart.paipan,
            engine_version=chart.engine_version,
            created_at=chart.created_at,
            updated_at=chart.updated_at,
        ),
        cache_slots=slots,
        cache_stale=paipan_adapter.is_cache_stale(chart.engine_version),
        warnings=warnings or [],
    )


@router.get("", response_model=ChartListResponse)
async def list_charts_endpoint(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> ChartListResponse:
    rows = await chart_service.list_charts(db, user)
    return ChartListResponse(items=[
        ChartListItem(
            id=r.id,
            label=r.label,
            engine_version=r.engine_version,
            cache_stale=paipan_adapter.is_cache_stale(r.engine_version),
            created_at=r.created_at,
            updated_at=r.updated_at,
        ) for r in rows
    ])


@router.post("", response_model=ChartResponse, status_code=status.HTTP_201_CREATED)
async def create_chart_endpoint(
    body: ChartCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> ChartResponse:
    try:
        chart, warnings = await chart_service.create_chart(db, user, body)
        await db.commit()
    except ServiceError as e:
        await db.rollback()
        raise _http_error(e)
    return await _chart_to_response(chart, db=db, warnings=warnings)


@router.get("/{chart_id}", response_model=ChartResponse)
async def get_chart_endpoint(
    chart_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> ChartResponse:
    try:
        chart = await chart_service.get_chart(db, user, chart_id)
    except ServiceError as e:
        raise _http_error(e)
    return await _chart_to_response(chart, db=db)


# 缓存版本号 — 单一真理源在 classics_polisher.CLASSICS_CACHE_VERSION,
# 两处用 (这里 + chat_classics_inject) 都从那儿引。和 frontend useAppStore
# 的 CLASSICS_VERSION 是两套独立 key（一个磁盘缓存的 schema 标记，一个
# 浏览器的本地存储版本），改动节奏可以不同步。
_CLASSICS_CACHE_VERSION = classics_polisher.CLASSICS_CACHE_VERSION


@router.get(
    "/{chart_id}/classics",
    response_model=ChartClassicsResponse,
    response_model_exclude_none=True,
)
async def get_chart_classics_endpoint(
    chart_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> ChartClassicsResponse:
    """命盘的"古书定调" — 双 pool 并行检索 + LLM polish 大约 30–40s，
    所以结果会持久化到 chart_cache (kind='classics', key='v2')。
    下次同一命盘请求直接读 cache。"""
    try:
        chart = await chart_service.get_chart(db, user, chart_id)
    except ServiceError as e:
        raise _http_error(e)

    cache_key = _CLASSICS_CACHE_VERSION
    cached_row = (await db.execute(
        select(ChartCache).where(
            ChartCache.chart_id == chart_id,
            ChartCache.kind == "classics",
            ChartCache.key == cache_key,
        )
    )).scalar_one_or_none()
    if cached_row is not None and cached_row.content:
        try:
            cached_payload = json.loads(cached_row.content)
            return ChartClassicsResponse(**cached_payload)
        except (ValueError, TypeError):
            # 缓存损坏 → 重新跑
            pass

    paipan = dict(chart.paipan or {})
    paipan["gender"] = (chart.birth_input or {}).get("gender", "")

    # 两个 pool 并行检索
    persona_hits, verdict_hits = await asyncio.gather(
        retrieval_service.retrieve_for_chart(paipan, "persona"),
        retrieval_service.retrieve_for_chart(paipan, "verdict"),
        return_exceptions=False,
    )

    payload = await classics_polisher.polish_classics_for_chart(
        paipan, persona_hits, verdict_hits,
    )
    response = ChartClassicsResponse(**payload)

    # 仅在拿到实际内容时才写缓存。LLM 非确定性偶尔会两条 pool 都返 null;
    # 如果把 null 也缓存下来,用户就被锁在空态直到 cache version bump。
    # 不缓存 null = 下次请求重跑 polish, 多刷几次大概率撞到 yes。
    if response.persona is not None or response.verdict is not None:
        serialized = response.model_dump_json(exclude_none=True)
        upsert = pg_insert(ChartCache).values(
            chart_id=chart_id,
            kind="classics",
            key=cache_key,
            content=serialized,
            model_used=None,
            tokens_used=None,
        ).on_conflict_do_update(
            constraint="uq_chart_cache_slot",
            set_={"content": serialized},
        )
        await db.execute(upsert)
        await db.commit()

    return response


@router.patch("/{chart_id}", response_model=ChartResponse)
async def patch_chart_endpoint(
    chart_id: UUID,
    body: ChartLabelUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> ChartResponse:
    try:
        chart = await chart_service.update_label(db, user, chart_id, body.label)
        await db.commit()
    except ServiceError as e:
        await db.rollback()
        raise _http_error(e)
    return await _chart_to_response(chart, db=db)


@router.delete("/{chart_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chart_endpoint(
    chart_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    try:
        await chart_service.soft_delete(db, user, chart_id)
        await db.commit()
    except ServiceError as e:
        await db.rollback()
        raise _http_error(e)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{chart_id}/restore", response_model=ChartResponse)
async def restore_chart_endpoint(
    chart_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> ChartResponse:
    try:
        chart = await chart_service.restore(db, user, chart_id)
        await db.commit()
    except ServiceError as e:
        await db.rollback()
        raise _http_error(e)
    return await _chart_to_response(chart, db=db)


@router.post("/{chart_id}/recompute", response_model=ChartResponse)
async def recompute_endpoint(
    chart_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> ChartResponse:
    try:
        chart, warnings = await chart_service.recompute(db, user, chart_id)
        await db.commit()
    except ServiceError as e:
        await db.rollback()
        raise _http_error(e)
    return await _chart_to_response(chart, db=db, warnings=warnings)


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.post("/{chart_id}/verdicts")
async def verdicts_endpoint(
    chart_id: UUID,
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    try:
        chart = await chart_service.get_chart(db, user, chart_id)
    except ServiceError as e:
        raise _http_error(e)
    cache = await chart_llm_service.get_cache_row(db, chart.id, "verdicts", "")
    ticket = None
    if cache and force:
        ticket_dep = check_quota("verdicts_regen")
        ticket = await ticket_dep(user=user, db=db)

    async def _gen():
        async for raw in chart_llm_service.stream_chart_llm(
            db, user, chart,
            kind="verdicts", key="", force=force,
            cache_row=cache, ticket=ticket,
            build_messages=prompts_verdicts.build_messages,
            retrieval_kind="meta",
            temperature=0.7, max_tokens=12000, tier="primary",
        ):
            yield raw
        await db.commit()

    return StreamingResponse(_gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/{chart_id}/sections")
async def sections_endpoint(
    chart_id: UUID, body: SectionBody,
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    try:
        chart = await chart_service.get_chart(db, user, chart_id)
    except ServiceError as e:
        raise _http_error(e)
    cache = await chart_llm_service.get_cache_row(db, chart.id, "section", body.section)
    ticket = None
    if cache and force:
        ticket_dep = check_quota("section_regen")
        ticket = await ticket_dep(user=user, db=db)

    async def _gen():
        async for raw in chart_llm_service.stream_chart_llm(
            db, user, chart,
            kind="section", key=body.section, force=force,
            cache_row=cache, ticket=ticket,
            build_messages=partial(prompts_sections.build_messages, section=body.section),
            retrieval_kind=f"section:{body.section}",
            temperature=0.7, max_tokens=12000, tier="primary",
        ):
            yield raw
        await db.commit()

    return StreamingResponse(_gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/{chart_id}/dayun/{index}")
async def dayun_endpoint(
    chart_id: UUID, index: int,
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    if index < 0:
        raise HTTPException(
            status_code=422,
            detail={"code": "VALIDATION", "message": f"index must be ≥ 0, got {index}"},
        )
    try:
        chart = await chart_service.get_chart(db, user, chart_id)
    except ServiceError as e:
        raise _http_error(e)
    _dayun_raw = chart.paipan.get("dayun") or {}
    dayun_list = _dayun_raw.get("list") if isinstance(_dayun_raw, dict) else list(_dayun_raw)
    dayun_count = len(dayun_list or [])
    if index >= dayun_count:
        raise HTTPException(
            status_code=422,
            detail={"code": "VALIDATION",
                    "message": f"dayun index {index} out of range ({dayun_count})"},
        )

    key = str(index)
    cache = await chart_llm_service.get_cache_row(db, chart.id, "dayun_step", key)
    ticket = None
    if cache and force:
        ticket_dep = check_quota("dayun_regen")
        ticket = await ticket_dep(user=user, db=db)

    async def _gen():
        async for raw in chart_llm_service.stream_chart_llm(
            db, user, chart,
            kind="dayun_step", key=key, force=force,
            cache_row=cache, ticket=ticket,
            build_messages=partial(prompts_dayun_step.build_messages, step_index=index),
            retrieval_kind="dayun_step",
            temperature=0.7, max_tokens=12000, tier="primary",
        ):
            yield raw
        await db.commit()

    return StreamingResponse(_gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/{chart_id}/liunian")
async def liunian_endpoint(
    chart_id: UUID, body: LiunianBody,
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    try:
        chart = await chart_service.get_chart(db, user, chart_id)
    except ServiceError as e:
        raise _http_error(e)
    _dayun_raw2 = chart.paipan.get("dayun") or {}
    dayun = _dayun_raw2.get("list") if isinstance(_dayun_raw2, dict) else list(_dayun_raw2)
    dayun = dayun or []
    if body.dayun_index >= len(dayun):
        raise HTTPException(
            status_code=422,
            detail={"code": "VALIDATION", "message": "dayun_index out of range"},
        )

    key = f"{body.dayun_index}:{body.year_index}"
    cache = await chart_llm_service.get_cache_row(db, chart.id, "liunian", key)
    ticket = None
    if cache and force:
        ticket_dep = check_quota("liunian_regen")
        ticket = await ticket_dep(user=user, db=db)

    async def _gen():
        async for raw in chart_llm_service.stream_chart_llm(
            db, user, chart,
            kind="liunian", key=key, force=force,
            cache_row=cache, ticket=ticket,
            build_messages=partial(
                prompts_liunian.build_messages,
                dayun_index=body.dayun_index, year_index=body.year_index,
            ),
            retrieval_kind="liunian",
            temperature=0.7, max_tokens=12000, tier="primary",
        ):
            yield raw
        await db.commit()

    return StreamingResponse(_gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/{chart_id}/chips")
async def chips_endpoint(
    chart_id: UUID,
    conversation_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    try:
        chart = await chart_service.get_chart(db, user, chart_id)
    except ServiceError as e:
        raise _http_error(e)

    async def _gen():
        async for raw in chart_chips_service.stream_chips(
            db, user, chart, conversation_id=conversation_id
        ):
            yield raw
        await db.commit()

    return StreamingResponse(_gen(), media_type="text/event-stream", headers=_SSE_HEADERS)
