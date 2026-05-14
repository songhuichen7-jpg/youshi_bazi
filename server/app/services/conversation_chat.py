"""Stage 1+2 orchestrator. NOTE: spec §5.

Pattern mirrors app.services.chart_llm.stream_chart_llm: commit-before-done.
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator
from uuid import UUID

import json
import logging

import anyio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.core.distributed_lock import LockBusyError, named_lock
from app.llm.client import chat_once_with_fallback, chat_stream_with_fallback
from app.llm.events import sse_pack

_log = logging.getLogger(__name__)
from app.llm.logs import insert_llm_usage_log
from app.models.user import User
from app.prompts import expert as prompts_expert
from app.retrieval2.service import retrieve_for_chart, retrieve_for_chart_compound  # noqa: F401 — kept for legacy fallback inside composer
from app.retrieval3 import compose as compose_retrieval3
from app.services import conversation as conv_service
from app.services import message as msg_svc
from app.services import conversation_memory as memory_svc
from app.services.chat_router import classify
from app.services.exceptions import UpstreamLLMError
from app.services.quota import QuotaTicket


# 跨标签 / 跨请求并发保护:同一个 conversation_id 同一时间只允许一条
# stream 在跑。多标签场景(用户两标签同时发同一 conv 的消息)以前会
# 在服务端交错插 user/assistant 行,DB 里就出现 [u1, u2, a2, a1] 这种
# 错位顺序。
#
# 锁实现走 app.core.distributed_lock — Redis 可用时跨 worker 共享 (生
# 产多 worker 部署的正确语义),不可用时退化到 in-memory asyncio.Lock
# (本地 dev / 单 worker prod 行为跟改造前一致)。
# TTL 设 180s — 比最长合理 stream 时长稍宽,worker 崩溃也能在 3 分钟内
# 自动释放,不会出现"锁泄露用户永远发不出消息"。


_LEGACY_NO_RETRIEVAL_INTENTS = {"chitchat", "media", "appearance"}

# 续写场景识别：user 这一轮发了下面任一短语，且上一条 assistant 的
# meta.finish_reason == "length"（被 max_tokens 截断），就给 system prompt
# 追加一段"直接从断点接续写"的指令，避免模型当成新对话从头讲。
_CONTINUATION_TRIGGERS: frozenset[str] = frozenset({
    "继续", "继续写", "继续写下去", "继续写完", "写完",
    "接着", "接着说", "接着写", "接下去",
    "续写", "go on", "continue",
})

_CONTINUATION_HINT = """

【续写场景 — 上一条回答被截断，直接接续写】
上一条 assistant 回答因到达 max_tokens 输出上限被强制截断（finish_reason="length"），现在 user 发"继续"是为了让你接着写完。

要求：
- 直接从上一段最后一个字之后接着往下写，第一个字就是上一段的下一个字
- 不要重新打招呼、不要"好的"/"我接着说"这类开场、不要复述前文、不要总结
- 上一段可能停在半句话甚至逗号后，你就从那个位置自然续写完那句话再往下展开
- 写完之前主动收尾，避免再被截断；如果内容确实长，按结构分块，写到自然结束就停"""


def _is_continuation_request(message: str, last_finish_reason: str | None) -> bool:
    """True 当且仅当 user 这轮是短"继续"类指令 + 上一条 assistant 没正常结束。

    覆盖两种"上一条没写完"场景：
    - "length"   → max_tokens 截断（前端 banner "续写"按钮）
    - "stop_user" → 用户主动点了停止（前端 banner "接着写"按钮）
    两种情况都希望模型从断点处接续而不是从头讲。
    """
    if last_finish_reason not in ("length", "stop_user"):
        return False
    text = (message or "").strip().lower()
    # 限制在短促指令——长 user message 即使含"继续"二字也不是续写请求
    if not text or len(text) > 12:
        return False
    return text in _CONTINUATION_TRIGGERS


def _plan_needs_classics(route_plan: dict, effective_intent: str) -> bool:
    retrieval_plan = route_plan.get("retrieval_plan")
    if isinstance(retrieval_plan, dict) and isinstance(retrieval_plan.get("enabled"), bool):
        return bool(retrieval_plan.get("enabled"))
    needs = route_plan.get("needs")
    if isinstance(needs, dict) and isinstance(needs.get("classics"), bool):
        return bool(needs.get("classics"))
    return effective_intent not in _LEGACY_NO_RETRIEVAL_INTENTS


def _plan_retrieval_focus(route_plan: dict) -> list[str]:
    retrieval_plan = route_plan.get("retrieval_plan")
    if not isinstance(retrieval_plan, dict):
        return []
    focus = retrieval_plan.get("focus")
    if not isinstance(focus, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in focus:
        text = " ".join(str(item or "").split())[:24]
        if not text or text in seen:
            continue
        out.append(text)
        seen.add(text)
        if len(out) >= 8:
            break
    return out


def _plan_disable_thinking(route_plan: dict) -> bool:
    artifact = route_plan.get("artifact")
    return bool(isinstance(artifact, dict) and artifact.get("enabled") is True)


def _paipan_with_birth_context(chart) -> dict:
    paipan = dict(chart.paipan or {})
    birth = chart.birth_input if isinstance(chart.birth_input, dict) else {}
    gender = birth.get("gender")
    if gender and not paipan.get("gender"):
        paipan["gender"] = gender
    if birth:
        existing = paipan.get("birthInput") if isinstance(paipan.get("birthInput"), dict) else {}
        paipan["birthInput"] = {**existing, **birth}
    return paipan


async def _generate_suggestions(
    *,
    user_message: str,
    assistant_answer: str,
    recent_history: list[dict],
) -> list[str]:
    """Generate 3 follow-up question suggestions using the fast LLM tier.

    Returns a list of up to 3 question strings, or empty list on failure.
    Best-effort only — callers must catch all exceptions.
    """
    history_lines = "\n".join(
        f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content'][:150]}"
        for m in recent_history[-4:]
    ) or "（这是对话的第一轮）"
    prompt = (
        f"对话记录：\n{history_lines}\n\n"
        f"用户刚才问：{user_message[:200]}\n\n"
        f"AI刚才答：\n{assistant_answer[:500]}\n\n"
        "你非常懂命理，也非常懂人。\n"
        "现在，想象你在读这位用户的心——他看完这个回答之后，脑子里自然会浮现出什么疑问？\n\n"
        "给出2-3个最真实的追问。好的追问是这样的：\n"
        "- 用户看到会想「对，这正是我接下来想问的」\n"
        "- 紧扣回答里提到的某个具体内容（某个说法、某个时间节点、某个建议）\n"
        "- 是真实的好奇，不是为了提问而提问\n"
        "- 口语化、自然成句，不超过20字\n\n"
        "如果这个话题已经说透了，才可以顺着用户当前的处境延伸到相关方向——"
        "但要有连接感，不是硬转话题。\n\n"
        "只返回JSON数组：[\"问题1\", \"问题2\", \"问题3\"]，不要其他内容"
    )
    text, model_used = await chat_once_with_fallback(
        messages=[{"role": "user", "content": prompt}],
        tier="fast",
        temperature=0.8,
        max_tokens=200,
        disable_thinking=True,
    )
    _log.info("suggestions LLM raw (model=%s): %r", model_used, text[:300])
    raw = text.strip()
    # 去掉可能的 ```json ... ``` 代码块包裹
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start < 0 or end <= start:
        _log.warning("suggestions: no JSON array in LLM output: %r", text[:200])
        return []
    try:
        items = json.loads(raw[start:end])
    except json.JSONDecodeError as e:
        _log.warning("suggestions: JSON parse failed (%s): %r", e, raw[start:end][:200])
        return []
    if not isinstance(items, list):
        return []
    cleaned = [str(q).strip() for q in items if q and str(q).strip()][:3]
    _log.info("suggestions generated: %s", cleaned)
    return cleaned


async def stream_message(
    *, db: AsyncSession, user: User, conversation_id: UUID,
    chart, message: str, bypass_divination: bool,
    ticket: QuotaTicket,
    client_context: dict | None = None,
    regenerate: bool = False,
) -> AsyncIterator[bytes]:
    """Generator yielding SSE-encoded bytes. NOTE: spec §5.

    regenerate=True 表示这是"重新回答"——不 insert 新 user，删旧 assistant，
    复用现有 user 重新走 stream。前端 chatHistory 已经把 last assistant 重置
    为空 placeholder，后端这边对齐。
    """
    try:
        async with named_lock(f"conv:{conversation_id}", ttl=180):
            async for chunk in _stream_message_locked(
                db=db, user=user, conversation_id=conversation_id,
                chart=chart, message=message,
                bypass_divination=bypass_divination,
                ticket=ticket, client_context=client_context,
                regenerate=regenerate,
            ):
                yield chunk
    except LockBusyError:
        # 已经有一条 stream 在跑这个 conv — 拒绝并发,避免 DB 错位写入
        yield sse_pack({
            "type": "error",
            "code": "CONVERSATION_BUSY",
            "message": "这条对话另一个回答正在生成中,请等它完成或停止后再发。",
        })
        return


async def _stream_message_locked(
    *, db: AsyncSession, user: User, conversation_id: UUID,
    chart, message: str, bypass_divination: bool,
    ticket: QuotaTicket,
    client_context: dict | None = None,
    regenerate: bool = False,
) -> AsyncIterator[bytes]:
    """主流程 — 假设外面已经拿到 conv lock。"""
    if regenerate:
        # 重新回答 — 删旧 assistant，不插新 user。前端 chatHistory 已经把
        # last assistant 重置为空 placeholder，DB 这边对齐避免重复 user。
        # router_history / context_history 要在删旧 assistant 之后 fetch，
        # 否则 history 会带上即将被删的旧回答污染 LLM prompt。
        await msg_svc.delete_latest_assistant(db, conversation_id=conversation_id)
        await db.commit()
        router_history = await msg_svc.recent_chat_history(db, conversation_id=conversation_id, limit=4)
        history = await msg_svc.context_chat_history(db, conversation_id=conversation_id)
        memory_summary = await memory_svc.get_summary(db, conversation_id=conversation_id)
    else:
        router_history = await msg_svc.recent_chat_history(db, conversation_id=conversation_id, limit=4)
        history = await msg_svc.context_chat_history(db, conversation_id=conversation_id)
        memory_summary = await memory_svc.get_summary(db, conversation_id=conversation_id)

        await msg_svc.insert(db, conversation_id=conversation_id, role="user", content=message)
        # SSE answers can run for tens of seconds and may be cancelled by refreshes,
        # route changes, or network drops. Commit the user turn before the long work
        # starts so a cancelled stream cannot erase the whole turn from history.
        await db.commit()

    routed = await classify(
        db=db, user=user, chart_id=chart.id,
        message=message, history=router_history,
    )
    # 计算 retrieval_kinds: primary + secondary 去重(去掉 chitchat/divination
    # 这种不参与 retrieval 的). media 保留 — media policy 有自己的检索逻辑
    # (依靠 needs.classics 判断是否实际跑)。这是给前端展示 + 后端检索共用的 list。
    retrieval_kinds: list[str] = []
    seen_kinds: set[str] = set()
    for k in [routed["intent"], *routed.get("secondary_intents", [])]:
        if k and k not in seen_kinds and k not in {"chitchat", "divination"}:
            retrieval_kinds.append(k)
            seen_kinds.add(k)

    yield sse_pack({
        "type": "intent",
        "intent": routed["intent"],
        "reason": routed["reason"],
        "source": routed["source"],
        "artifact": routed.get("artifact"),
        "secondary_intents": routed.get("secondary_intents", []),
        "retrieval_kinds": retrieval_kinds,
        "needs": routed.get("needs"),
        "retrieval_plan": routed.get("retrieval_plan"),
        "answer_plan": routed.get("answer_plan"),
    })

    intent = routed["intent"]

    if intent == "divination" and not bypass_divination:
        await msg_svc.insert(db, conversation_id=conversation_id, role="cta",
                              content=None, meta={"question": message})
        yield sse_pack({"type": "redirect", "to": "gua", "question": message})
        try:
            await ticket.commit()
        except Exception as e:  # noqa: BLE001 — quota race or other commit failure
            yield sse_pack({"type": "error", "code": "QUOTA_EXCEEDED", "message": str(e)})
            return
        yield sse_pack({"type": "done", "full": ""})
        return

    effective_intent = "other" if intent == "divination" else intent

    if bypass_divination:
        await msg_svc.delete_last_cta(db, conversation_id=conversation_id)

    retrieved: list[dict] = []
    retrieval_focus = _plan_retrieval_focus(routed)
    if _plan_needs_classics(routed, effective_intent):
        try:
            paipan_for_retrieval = _paipan_with_birth_context(chart)
            # retrieval3 composer: 7 个家族 deterministic 检索 + retrieval2
            # 兜底 (理论原则/案例)。家族检索 0 LLM, 兜底走原 selector — 整体
            # 比纯 retrieval2 高 3-4 倍 section_hit (920-query baseline 验证)。
            cards = await compose_retrieval3(
                paipan_for_retrieval,
                intent=effective_intent,
                secondary_intents=routed.get("secondary_intents") or [],
                user_message=message,
                retrieval_focus=retrieval_focus,
            )
            # composer 真实返回 EvidenceCard,但旧测试 monkeypatch 用 V1Hit dict —
            # 同时容忍两种形态,生产代码走 to_v1_hit(),测试 dict 直接通过
            retrieved = [c.to_v1_hit() if hasattr(c, "to_v1_hit") else c for c in cards]
        except Exception:  # noqa: BLE001 — retrieval is best-effort
            retrieved = []
    if retrieved:
        sources = " + ".join(h.get("source", "?") for h in retrieved)
        yield sse_pack({"type": "retrieval", "source": sources})

    # Hepan-aware context — 主 chat 可以选中一条具体合盘关系。选中时注入
    # 双方命盘 + 合盘卡片信息；未选中时保留旧的“最近合过谁”简表。
    # conv.hepan_slug (DB-authoritative) wins over client_context (legacy
    # URL-param fallback). See app.services.hepan.context.hepan_context_for_user.
    from app.services.hepan.context import hepan_context_for_user
    conv = await conv_service.get_conversation(db, user, conversation_id)
    hepan_summary = await hepan_context_for_user(
        db, user.id,
        client_context=client_context,
        conv_hepan_slug=getattr(conv, "hepan_slug", None),
    )

    # 古书定调 — 懒加载 + 非阻塞。Cache 命中即注入；未命中返回空串
    # (第一次访问命盘还没生成完时即此情况)，不阻塞对话。
    from app.services.chat_classics_inject import maybe_classics_segment
    classics_summary = await maybe_classics_segment(db, chart.id)

    paipan_for_prompt = _paipan_with_birth_context(chart)
    messages_llm = prompts_expert.build_messages(
        paipan=paipan_for_prompt, history=history,
        user_message=message, intent=effective_intent,
        retrieved=retrieved,
        client_context=client_context,
        memory_summary=memory_summary,
        hepan_summary=hepan_summary,
        classics_summary=classics_summary,
        route_plan=routed,
    )

    # 续写场景检测：上一条 assistant 被截断 + 本轮 user 是短"继续"指令 → 给
    # system prompt 末尾追加续写指令。这是 max_tokens=12000 之外的兜底——12000
    # 仍可能撞墙时，"续写"按钮能让模型从断点处自然接续而不是从头开始。
    last_finish_reason = await msg_svc.latest_assistant_finish_reason(
        db, conversation_id=conversation_id,
    )
    if _is_continuation_request(message, last_finish_reason):
        if messages_llm and messages_llm[0].get("role") == "system":
            messages_llm[0]["content"] = messages_llm[0]["content"] + _CONTINUATION_HINT

    accumulator = ""
    model_used: str | None = None
    prompt_tok = completion_tok = total_tok = 0
    finish_reason: str | None = None
    t_start = time.monotonic()
    err: UpstreamLLMError | None = None
    # exited_normally=True 时（success / LLM 错 / quota race 三类显式 return
    # 路径），finally 不会落 partial。只有走 GeneratorExit / CancelledError
    # 这种 abort 路径才会 partial 持久化 — LLM 错 / quota race 是 "billing
    # 公平性 + 未完成的回答"语义上不该留 assistant 行（test 也明确要求 no
    # assistant on quota race）。
    exited_normally = False

    try:
        try:
            async for ev in chat_stream_with_fallback(
                messages=messages_llm, tier="primary",
                temperature=0.7, max_tokens=12000,
                first_delta_timeout_ms=settings.llm_stream_first_delta_ms,
                disable_thinking=_plan_disable_thinking(routed),
            ):
                t = ev["type"]
                if t == "model":
                    model_used = ev["modelUsed"]
                    yield sse_pack(ev)
                elif t == "delta":
                    accumulator += ev["text"]
                    yield sse_pack(ev)
                elif t == "thinking":
                    # 透传，不入 accumulator —— 思考过程只给 UI 流式显示，不持久。
                    yield sse_pack(ev)
                elif t == "done":
                    prompt_tok = ev.get("prompt_tokens", 0)
                    completion_tok = ev.get("completion_tokens", 0)
                    total_tok = ev.get("tokens_used", 0)
                    finish_reason = ev.get("finish_reason")
        except UpstreamLLMError as e:
            err = e
            yield sse_pack({"type": "error", "code": e.code, "message": e.message})

        duration_ms = int((time.monotonic() - t_start) * 1000)

        if err is not None:
            await insert_llm_usage_log(
                db, user_id=user.id, chart_id=chart.id,
                endpoint="chat:expert", model=model_used,
                prompt_tokens=None, completion_tokens=None,
                duration_ms=duration_ms, error=f"{err.code}: {err.message}",
                retrieval_claims=retrieved or None,
            )
            exited_normally = True
            return

        try:
            await ticket.commit()
        except Exception as e:  # noqa: BLE001 — quota race or other commit failure
            yield sse_pack({"type": "error", "code": "QUOTA_EXCEEDED", "message": str(e)})
            await insert_llm_usage_log(
                db, user_id=user.id, chart_id=chart.id,
                endpoint="chat:expert", model=model_used,
                prompt_tokens=None, completion_tokens=None,
                duration_ms=duration_ms, error=f"QUOTA_EXCEEDED: {e}",
                retrieval_claims=retrieved or None,
            )
            exited_normally = True
            return

        assistant_msg = await msg_svc.insert(
            db, conversation_id=conversation_id, role="assistant",
            content=accumulator,
            meta={
                "intent": effective_intent,
                "model_used": model_used,
                "retrieval_source": (
                    " + ".join(h.get("source", "?") for h in retrieved) if retrieved else None
                ),
                "artifact": routed.get("artifact"),
                # finish_reason == "length" 表示被 max_tokens 截断；前端据此显示
                # 截断警示 + 续写按钮。"stop" / None 时此字段省略，避免污染老数据。
                **({"finish_reason": finish_reason} if finish_reason and finish_reason != "stop" else {}),
            },
        )
        await insert_llm_usage_log(
            db, user_id=user.id, chart_id=chart.id,
            endpoint="chat:expert", model=model_used,
            prompt_tokens=prompt_tok, completion_tokens=completion_tok,
            duration_ms=duration_ms, retrieval_claims=retrieved or None,
        )
        yield sse_pack({
            "type": "done", "full": accumulator, "tokens_used": total_tok,
            "finish_reason": finish_reason,
        })
        _log.info(
            "suggestions gate: finish_reason=%r accumulator_len=%d intent=%r",
            finish_reason, len(accumulator or ""), effective_intent,
        )
        if finish_reason in (None, "stop") and accumulator:
            try:
                suggestions = await _generate_suggestions(
                    user_message=message,
                    assistant_answer=accumulator,
                    recent_history=history[-6:],
                )
                if suggestions:
                    _log.info("suggestions yielded: %d items", len(suggestions))
                    # 落到 meta 里 — 否则 stream 结束后 AppShell 的 hydration
                    # 会拿 DB 数据覆盖内存里的 suggestions 字段，chip 立刻消失。
                    # EncryptedJSONB 列重新赋整个 dict + flag_modified 强制脏标记，
                    # 否则 SQLAlchemy 可能识别不到 mutable 容器的变化。
                    assistant_msg.meta = {**(assistant_msg.meta or {}), "suggestions": suggestions}
                    flag_modified(assistant_msg, "meta")
                    await db.flush()
                    yield sse_pack({"type": "suggestions", "items": suggestions})
                else:
                    _log.warning("suggestions: empty list, nothing yielded")
            except Exception:  # noqa: BLE001 — best-effort, never block
                _log.warning("suggestions generation failed", exc_info=True)
        await memory_svc.maybe_refresh_summary(
            db,
            user=user,
            chart=chart,
            conversation_id=conversation_id,
        )
        exited_normally = True
    finally:
        # 这里的语义：
        #   · exited_normally=True → success / LLM 错 / quota race 三种正常退
        #     出，不动 partial（quota race 路径 test 明确要求 no assistant）
        #   · exited_normally=False + accumulator 非空 → 客户端 abort
        #     (GeneratorExit/CancelledError)。用户已经看到屏幕上几百字了，
        #     落一条 interrupted=True 的 assistant 行避免下次刷历史看到悬空
        #     的 user message
        # commit 也在这里 — caller 的 await db.commit() 在 abort 路径不会执
        # 行；user message 前面已经提前提交，这里负责保存 partial assistant
        # 和清理本轮后续写入。完成路径 caller 会再 commit 一遍，SQLAlchemy
        # 二次 commit 是 no-op，安全。
        try:
            with anyio.CancelScope(shield=True):
                if not exited_normally and accumulator:
                    try:
                        await msg_svc.insert(
                            db, conversation_id=conversation_id, role="assistant",
                            content=accumulator,
                            meta={
                                "intent": effective_intent,
                                "model_used": model_used,
                                "interrupted": True,
                                # finish_reason="stop_user" 让前端跟 max_tokens 截断
                                # （"length"）走同一套 banner 渠道，但按钮文字区分：
                                # "续写" vs "接着写"。详见 _serverMsgToUiMsg。
                                "finish_reason": "stop_user",
                                "artifact": routed.get("artifact"),
                            },
                        )
                    except Exception:  # noqa: BLE001 — best-effort persistence
                        pass
                await db.commit()
        except Exception:  # noqa: BLE001 — db 可能已经被 caller 关掉
            pass
