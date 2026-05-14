import { useEffect, useRef, useState } from 'react';
import { useAppStore } from '../store/useAppStore';
import { streamLiunian } from '../lib/api';
import { RichText } from './RefChip';
import ErrorState from './ErrorState';
import { friendlyError } from '../lib/errorMessages';
import { buildLiunianPanel } from '../lib/timingPanels';
import { devLog } from '../lib/devLog';

function isAbort(e) {
  return e?.name === 'AbortError' || /aborted|abort/i.test(String(e?.message || e));
}

export default function LiunianBody({ dayunIdx, yearIdx }) {
  const key = `${dayunIdx}-${yearIdx}`;
  const cached = useAppStore((s) => s.liunianCache[key]);
  const setCache = useAppStore((s) => s.setLiunianCache);
  const deleteCache = useAppStore((s) => s.deleteLiunianCache);
  const setStreamingFlag = useAppStore((s) => s.setLiunianStreaming);
  const currentId = useAppStore((s) => s.currentId);
  const dayun = useAppStore((s) => s.dayun);

  const [text, setText] = useState(cached || '');
  const [error, setError] = useState(null);
  // 本地 streaming 标志 + AbortController — 让用户能中断当前生成。
  // mount / unmount / key-change 的 abort 由主 effect 的 cleanup 管理，
  // 跟 abortRef 区分开，避免 StrictMode 把刚启动的 stream 立刻 abort 掉。
  const [streaming, setStreaming] = useState(false);
  const [stoppedByUser, setStoppedByUser] = useState(false);
  // finish_reason === "length" → 被 max_tokens 截断；后端不写 cache + 不扣额。
  const [truncated, setTruncated] = useState(false);
  const abortRef = useRef(null);
  const [reloadNonce, setReloadNonce] = useState(0);
  const uiError = error ? friendlyError(error, 'liunian') : null;

  useEffect(() => {
    setText(cached || '');
    setError(null);
    setStoppedByUser(false);
    const timer = setTimeout(() => {
      document.getElementById(`liunian-body-${key}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }, 20);
    return () => clearTimeout(timer);
  }, [key, cached]);

  useEffect(() => {
    if (cached) return undefined;
    if (!currentId) return undefined;
    let cancelled = false;
    const controller = new AbortController();
    abortRef.current = controller;
    setStreaming(true);
    setStreamingFlag(true);
    setError(null);
    setText('');
    setStoppedByUser(false);
    setTruncated(false);

    let streamFinishReason = null;
    (async () => {
      try {
        const full = await streamLiunian(currentId, { dayun_index: dayunIdx, year_index: yearIdx }, {
          signal: controller.signal,
          onDelta: (_t, running) => { if (!cancelled) setText(running); },
          onDone: (_full, finishReason) => { streamFinishReason = finishReason; },
          onModel: (model) => devLog('[liunian] modelUsed=' + model),
          onRetrieval: (source) => devLog('[liunian] retrieval=' + source),
        });
        if (cancelled) return;
        if (!full.trim()) throw new Error('empty response');
        if (streamFinishReason === 'length') {
          // 截断不写 cache（后端也没写），保留 text 让用户看见，给重生入口
          setTruncated(true);
          setText(full);
        } else {
          setCache(key, full);
          setText(full);
        }
      } catch (e) {
        if (cancelled || isAbort(e)) return;
        console.error('[liunian] failed:', e);
        deleteCache(key);
        setError(e.message || String(e));
      } finally {
        if (!cancelled) {
          setStreaming(false);
          setStreamingFlag(false);
          if (abortRef.current === controller) abortRef.current = null;
        }
      }
    })();

    return () => {
      cancelled = true;
      try { controller.abort(); } catch { /* ignore */ }
      setStreaming(false);
      setStreamingFlag(false);
      if (abortRef.current === controller) abortRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, cached, currentId, reloadNonce]);

  function onStop() {
    setStoppedByUser(true);
    if (abortRef.current) {
      try { abortRef.current.abort(); } catch { /* ignore */ }
    }
    setStreaming(false);
    setStreamingFlag(false);
  }

  function onRetry() {
    deleteCache(key);
    setReloadNonce((n) => n + 1);
  }

  function onResume() {
    setReloadNonce((n) => n + 1);
  }

  const year = dayun?.[dayunIdx]?.years?.[yearIdx] || null;
  const panel = buildLiunianPanel(year, text);

  return (
    <section id={`liunian-body-${key}`} className="timing-panel timing-subpanel">
      <div className="timing-panel-head">
        <div className="timing-panel-kicker">{panel.kicker}</div>
        <div className="timing-panel-title serif">{panel.title}</div>
        {streaming ? (
          <button type="button" className="timing-stop-btn" onClick={onStop}>
            停止
          </button>
        ) : null}
      </div>

      {error ? (
        <ErrorState
          title={uiError.title}
          detail={uiError.detail}
          retryable={uiError.retryable}
          onRetry={uiError.retryable ? onRetry : undefined}
        />
      ) : !text && streaming ? (
        // 初始等首个 delta — 还没有任何文字时给一个柔和的"正在思考"动画
        <div className="skeleton-progress timing-loading" role="status" aria-live="polite">
          <div className="skeleton-progress-label">正在细看这一年</div>
          <div className="skeleton-progress-sublabel">会给你看这一年的主压力、机会点和需要留心的地方。</div>
          <div className="skeleton-lines">
            <div className="skeleton-line skeleton-pulse" style={{ width: '86%' }} />
            <div className="skeleton-line skeleton-pulse" style={{ width: '79%' }} />
            <div className="skeleton-line skeleton-pulse" style={{ width: '68%' }} />
          </div>
        </div>
      ) : !text && stoppedByUser ? (
        // 用户主动停了 + 还没有任何已生成内容 — 给一个重新生成入口
        <div className="timing-stopped" role="status">
          <div className="timing-stopped-text">已停止生成</div>
          <button type="button" className="btn-inline" onClick={onResume}>重新生成</button>
        </div>
      ) : (
        <div className={'timing-body' + (streaming ? ' timing-body-streaming' : '')}>
          {panel.paragraphs.map((paragraph, paragraphIndex) => (
            <p className="timing-paragraph" key={paragraphIndex}>
              <RichText text={paragraph} />
              {streaming && paragraphIndex === panel.paragraphs.length - 1 ? (
                <span className="timing-caret" aria-hidden="true">▌</span>
              ) : null}
            </p>
          ))}
        </div>
      )}

      {truncated && !streaming ? (
        <div className="msg-truncated-banner">
          <span className="msg-truncated-icon" aria-hidden="true">⚠</span>
          <span className="msg-truncated-text">内容过长被截断（达到模型输出上限）— 未缓存，可重新生成</span>
          <button
            type="button"
            className="btn-inline msg-continue-btn"
            onClick={onRetry}
          >重新生成</button>
        </div>
      ) : null}
    </section>
  );
}
