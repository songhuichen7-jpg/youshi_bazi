/* eslint-disable react-hooks/set-state-in-effect */
import { useEffect, useRef, useState } from 'react';
import { useAppStore } from '../store/useAppStore';
import { renderMd } from '../lib/richText.jsx';
import ErrorState from './ErrorState';
import { friendlyError } from '../lib/errorMessages';
import { buildPersonaDisplay, buildVerdictDisplay } from '../lib/classics';
import ClassicsBookLoader from './ClassicsBookLoader';

// 古籍 retrieval + 双 pool LLM polish 串起来比较慢；超过这个阈值给用户
// 一个"还在翻 / 可重试"的兜底，不要让翻书 loader 永远转。
const SLOW_HINT_AFTER_MS = 22000;

export default function ClassicsPanel() {
  const classics = useAppStore((s) => s.classics);
  const currentId = useAppStore((s) => s.currentId);
  const loadClassics = useAppStore((s) => s.loadClassics);

  // 当 isPending 进入第 22s 时切到 true，文案 + 重试出现
  const [isSlow, setIsSlow] = useState(false);
  const pendingStartRef = useRef(null);

  useEffect(() => {
    setIsSlow(false);
    pendingStartRef.current = null;
  }, [currentId]);

  const status = classics?.status || 'idle';
  const persona = buildPersonaDisplay(classics?.persona);
  const verdict = buildVerdictDisplay(classics?.verdict);
  const error = classics?.lastError || null;
  const uiError = error ? friendlyError(error, 'classics') : null;

  // persona 是主体, verdict 是脚注。没 persona 时整个面板走空态 —
  // 单独一句判语没有上下文反而像 bug, 跟 chat_classics_inject 同款逻辑。
  const hasContent = !!persona;
  const isPending = (status === 'idle' || status === 'loading') && !hasContent;

  useEffect(() => {
    if (!isPending) {
      pendingStartRef.current = null;
      setIsSlow(false);
      return undefined;
    }
    if (pendingStartRef.current == null) pendingStartRef.current = Date.now();
    const elapsed = Date.now() - pendingStartRef.current;
    const remaining = Math.max(0, SLOW_HINT_AFTER_MS - elapsed);
    if (remaining === 0) {
      setIsSlow(true);
      return undefined;
    }
    const t = setTimeout(() => setIsSlow(true), remaining);
    return () => clearTimeout(t);
  }, [isPending, currentId]);

  return (
    <div className="classics-panel persona-panel">
      <div className="panel-head classics-head">
        <div>
          <div className="section-num">古 书 定 调</div>
          {hasContent ? (
            <div className="serif classics-title">古人是这样形容这种命的</div>
          ) : null}
        </div>
        {status === 'error' && currentId && uiError?.retryable ? (
          <button className="btn-inline" onClick={() => loadClassics(currentId)}>再试一次</button>
        ) : null}
      </div>

      {status === 'error' ? (
        <ErrorState
          title={uiError.title}
          detail={uiError.detail}
          retryable={uiError.retryable}
          onRetry={uiError.retryable && currentId ? () => loadClassics(currentId) : undefined}
        />
      ) : null}

      {isPending ? <ClassicsBookLoader isSlow={isSlow} /> : null}

      {persona ? (
        <article className="persona-card fade-in">
          <div className="persona-source">
            <span className="persona-book serif">{persona.book}</span>
            {persona.chapter ? <span className="persona-chapter serif">·{persona.chapter}</span> : null}
            {persona.section ? <span className="persona-section">{persona.section}</span> : null}
          </div>
          <div className="persona-quote serif">{renderMd(persona.quote)}</div>
          {persona.plain ? (
            <div className="persona-plain">
              <span className="persona-plain-label">白话：</span>
              {renderMd(persona.plain)}
            </div>
          ) : null}
          {persona.fit_note ? (
            <div className="persona-fit-note muted">{persona.fit_note}</div>
          ) : null}
        </article>
      ) : null}

      {persona && verdict ? (
        <div className="verdict-strip fade-in">
          <span className="verdict-divider">—— 古人定语 ——</span>
          <blockquote className="verdict-quote serif">「{verdict.quote}」</blockquote>
          <div className="verdict-source muted">——{verdict.book}·{verdict.chapter}</div>
        </div>
      ) : null}

      {!isPending && !hasContent && status !== 'error' ? (
        <div className="persona-empty muted">此盘古籍未见直接命例可对照。</div>
      ) : null}
    </div>
  );
}
