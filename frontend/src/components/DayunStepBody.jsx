import { useEffect, useRef, useState } from 'react';
import { useAppStore } from '../store/useAppStore';
import { streamDayunStep } from '../lib/api';
import LiunianBody from './LiunianBody';
import { RichText } from './RefChip';
import ErrorState from './ErrorState';
import { friendlyError } from '../lib/errorMessages';
import { buildDayunPanel } from '../lib/timingPanels';
import { devLog } from '../lib/devLog';

function isAbort(e) {
  return e?.name === 'AbortError' || /aborted|abort/i.test(String(e?.message || e));
}

export default function DayunStepBody({ idx }) {
  const cached = useAppStore((s) => s.dayunCache[idx]);
  const dayun = useAppStore((s) => s.dayun);
  const setDayunCache = useAppStore((s) => s.setDayunCache);
  const deleteDayunCache = useAppStore((s) => s.deleteDayunCache);
  const setDayunStreaming = useAppStore((s) => s.setDayunStreaming);
  const currentId = useAppStore((s) => s.currentId);

  const [text, setText] = useState(cached || '');
  const [error, setError] = useState(null);
  const [streaming, setStreaming] = useState(false);
  const [stoppedByUser, setStoppedByUser] = useState(false);
  // finish_reason === "length" → 模型被 max_tokens 截断。chart_llm 后端这种
  // 情况不写 cache + 不扣额；前端显示警示+重新生成按钮（onRetry 已存在）。
  const [truncated, setTruncated] = useState(false);
  // 当前正在跑的 stream 的 AbortController — 暴露给"停止"按钮。
  // 注意：mount/unmount/idx-change 的 abort 由下方主 effect 的 cleanup
  // 直接管理，**不**通过 abortRef，避免 StrictMode 的 double-effect 把
  // 自己刚开始的 stream 立刻 abort 掉。
  const abortRef = useRef(null);
  // 让用户主动 onStop / onResume / onRetry 触发重跑用的 nonce
  const [reloadNonce, setReloadNonce] = useState(0);

  useEffect(() => {
    setText(cached || '');
    setError(null);
    setStoppedByUser(false);
    const timer = setTimeout(() => {
      document.getElementById(`dayun-step-body-${idx}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }, 20);
    return () => clearTimeout(timer);
  }, [idx, cached]);

  // Stream 主 effect — setup 起 stream，cleanup abort。把"启动"和"清理"
  // 放在同一个 effect 里，让 React（包括 StrictMode 的 double-mount）的
  // setup/cleanup 配对永远是同一对 controller，不会出现 cleanup 误杀
  // 别的 setup 起的请求的情况。
  useEffect(() => {
    if (cached) return undefined;       // 已有缓存就不重跑
    if (!currentId) return undefined;
    let cancelled = false;
    const controller = new AbortController();
    abortRef.current = controller;
    setStreaming(true);
    setDayunStreaming(true);
    setError(null);
    setText('');
    setStoppedByUser(false);
    setTruncated(false);

    let streamFinishReason = null;
    (async () => {
      try {
        const full = await streamDayunStep(currentId, idx, {
          signal: controller.signal,
          // 实时把 delta 写进 text — 字逐段冒出来
          onDelta: (_t, running) => { if (!cancelled) setText(running); },
          onDone: (_full, finishReason) => { streamFinishReason = finishReason; },
          onModel: (model) => devLog('[dayun-step] modelUsed=' + model),
          onRetrieval: (source) => devLog('[dayun-step] retrieval=' + source),
        });
        if (cancelled) return;
        if (!full.trim()) throw new Error('empty response');
        // 截断时不写 cache（后端也没写），下次 mount/retry 会重新生成；显示警示
        if (streamFinishReason === 'length') {
          setTruncated(true);
          setText(full);
        } else {
          setDayunCache(idx, full);
          setText(full);
        }
      } catch (e) {
        if (cancelled || isAbort(e)) return;
        console.error('[dayun-step] failed:', e);
        deleteDayunCache(idx);
        setError(e.message || String(e));
      } finally {
        if (!cancelled) {
          setStreaming(false);
          setDayunStreaming(false);
          if (abortRef.current === controller) abortRef.current = null;
        }
      }
    })();

    return () => {
      cancelled = true;
      try { controller.abort(); } catch { /* ignore */ }
      // 切大运 / 卸载时如果 stream 还在，前面 finally 里不会跑（cancelled
      // 提前 return），需要在这里把 streaming 标志收尾，否则下一次 mount
      // 进来会看到残留的 streaming=true。
      setStreaming(false);
      setDayunStreaming(false);
      if (abortRef.current === controller) abortRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx, cached, currentId, reloadNonce]);

  function onStop() {
    setStoppedByUser(true);
    if (abortRef.current) {
      try { abortRef.current.abort(); } catch { /* ignore */ }
    }
    // 主 effect 的 cleanup 不会触发（deps 没变），手动收尾
    setStreaming(false);
    setDayunStreaming(false);
  }

  function onRetry() {
    deleteDayunCache(idx);
    setReloadNonce((n) => n + 1);
  }

  function onResume() {
    setReloadNonce((n) => n + 1);
  }

  const step = dayun[idx];
  const years = step?.years || [];
  const uiError = error ? friendlyError(error, 'dayun-step') : null;
  const panel = buildDayunPanel(step, text);

  return (
    <section id={`dayun-step-body-${idx}`} className="timing-panel timing-panel-dayun">
      <div className="timing-panel-head">
        <div className="timing-panel-kicker">{panel.kicker}</div>
        <div className="timing-panel-title serif">{panel.title}</div>
        {panel.meta ? <div className="timing-panel-meta">{panel.meta}</div> : null}
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
        // 等首个 delta 时的初始动画 — 一旦 text 有内容就切到逐字显示
        <div className="skeleton-progress timing-loading" role="status" aria-live="polite">
          <div className="skeleton-progress-label">正在推演这一步大运</div>
          <div className="skeleton-progress-sublabel">先给你整理这十年的主线、压力来源和后段转折。</div>
          <div className="skeleton-lines">
            <div className="skeleton-line skeleton-pulse" style={{ width: '92%' }} />
            <div className="skeleton-line skeleton-pulse" style={{ width: '88%' }} />
            <div className="skeleton-line skeleton-pulse" style={{ width: '84%' }} />
            <div className="skeleton-line skeleton-pulse" style={{ width: '72%' }} />
          </div>
        </div>
      ) : !text && stoppedByUser ? (
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

      {!error && !streaming && !truncated && text && years.length > 0 ? (
        <LiunianChips dayunIdx={idx} years={years} />
      ) : null}
    </section>
  );
}

function LiunianChips({ dayunIdx, years }) {
  const cache = useAppStore((s) => s.liunianCache);
  const openKey = useAppStore((s) => s.liunianOpenKey);
  const setOpenKey = useAppStore((s) => s.setLiunianOpenKey);
  const dayunStreaming = useAppStore((s) => s.dayunStreaming);
  // liunianStreaming 仍在 store 里，用来给 chat 等其它视图判断"流年还在写"
  // 但**这里不再据此 disable chip**：用户应该能在生成中切到别的已缓存
  // 流年（LiunianBody 卸载时会 abort 中途的请求）。
  const [shakeKey, setShakeKey] = useState(null);
  const shakeTimerRef = useRef(null);
  useEffect(() => () => {
    if (shakeTimerRef.current) clearTimeout(shakeTimerRef.current);
  }, []);

  const onChipClick = (yearIndex, isDisabled) => {
    const key = `${dayunIdx}-${yearIndex}`;
    if (isDisabled) {
      if (shakeTimerRef.current) clearTimeout(shakeTimerRef.current);
      setShakeKey(key);
      shakeTimerRef.current = setTimeout(() => setShakeKey(null), 420);
      return;
    }
    setOpenKey(openKey === key ? null : key);
  };

  const openYearIdx = openKey?.startsWith(`${dayunIdx}-`)
    ? Number(openKey.split('-')[1])
    : null;

  return (
    <div className="liunian-section">
      <div className="liunian-heading-row">
        <div className="liunian-heading">流 年</div>
        <div className="liunian-hint">再点具体年份，看这一运里的波动和转折。</div>
      </div>
      <div className="liunian-chip-grid">
        {years.map((year, yearIndex) => {
          const key = `${dayunIdx}-${yearIndex}`;
          const isCurrent = year.current;
          const isCached = !!cache[key];
          const isOpen = openKey === key;
          // 大运还在出文时，所有流年 chip 暂不响应（dayun 是流年的前提）；
          // 流年出文时，只锁住 *未缓存* 的 chip，已缓存的可以随时切回去看。
          const isDisabled = dayunStreaming && !isOpen;
          return (
            <button
              type="button"
              key={yearIndex}
              className={
                'ln-chip liunian-chip'
                + (isCurrent ? ' ln-cur' : '')
                + (isCached ? ' ln-cached' : '')
                + (isOpen ? ' active' : '')
                + (isDisabled ? ' disabled' : '')
                + (shakeKey === key ? ' ycell-shake' : '')
              }
              data-ref={`liunian.${year.year}`}
              onClick={() => onChipClick(yearIndex, isDisabled)}
              title={isDisabled ? '大运还在生成中，请稍候' : ''}
            >
              {year.year} {year.gz}
            </button>
          );
        })}
      </div>
      <div className="liunian-footnote">按公历年粗算（未切立春）</div>
      {openYearIdx !== null ? <LiunianBody dayunIdx={dayunIdx} yearIdx={openYearIdx} /> : null}
    </div>
  );
}
