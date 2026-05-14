import { useEffect, useRef, useState } from 'react';
import { useAppStore } from '../store/useAppStore';
import { streamGua } from '../lib/api';
import { RichText } from './RefChip';
import ErrorState from './ErrorState';
import { friendlyError } from '../lib/errorMessages';
import { devLog } from '../lib/devLog';

export default function Gua() {
  const current = useAppStore(s => s.gua?.current);
  const setGuaCurrent = useAppStore(s => s.setGuaCurrent);
  const pushGuaHistory = useAppStore(s => s.pushGuaHistory);
  const guaStreaming = useAppStore(s => s.guaStreaming);
  const setGuaStreaming = useAppStore(s => s.setGuaStreaming);
  const currentConversationId = useAppStore(s => s.currentConversationId);
  const bumpQuotaUsage = useAppStore(s => s.bumpQuotaUsage);
  const setAppNotice = useAppStore(s => s.setAppNotice);

  const [question, setQuestion] = useState('');
  const [streamingText, setStreamingText] = useState('');
  const [error, setError] = useState(null);
  const guaRef = useRef(null);
  const uiError = error ? friendlyError(error, 'gua') : null;

  // External trigger: ask other components to call this via window event
  useEffect(() => {
    function onCast(e) { castGua(e.detail?.question || question); }
    window.addEventListener('bazi:cast-gua', onCast);
    return () => window.removeEventListener('bazi:cast-gua', onCast);
  }, [question]); // eslint-disable-line react-hooks/exhaustive-deps

  async function castGua(q) {
    const txt = (q || question).trim();
    if (!txt || guaStreaming) return;
    setError(null);
    setStreamingText('');
    setGuaCurrent(null);
    setGuaStreaming(true);
    let gua = null;
    let full = '';
    try {
      if (!currentConversationId) throw new Error('请先创建一个对话');
      const final = await streamGua(currentConversationId, { question: txt }, {
        onGua: (g) => {
          gua = g;
          setGuaCurrent({ ...g, question: txt, body: '' });
          setTimeout(() => guaRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 50);
        },
        onDelta: (_t, running) => { full = running; setStreamingText(running); },
        onModel: (m) => devLog('[gua] modelUsed=' + m),
      });
      const finalEntry = { ...gua, question: txt, body: final || full, ts: Date.now() };
      setGuaCurrent(finalEntry);
      pushGuaHistory(finalEntry);
      setQuestion('');
      bumpQuotaUsage('gua');
    } catch (e) {
      console.error('[gua] failed:', e);
      setError(e.message || String(e));
      const ui = friendlyError(e, 'gua');
      if (ui.cta) setAppNotice(ui);
    } finally {
      setGuaStreaming(false);
      setStreamingText('');
    }
  }

  function onKey(e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); castGua(); } }

  const showText = streamingText || current?.body || '';

  return (
    <div ref={guaRef} className="gua-panel" style={{
      border:'1px solid #ddd', background:'#fffdf7', padding:16, marginBottom:16,
    }}>
      <div className="section-num" style={{ marginBottom:10 }}>起 一 卦</div>
      <div style={{ display:'flex', gap:8, marginBottom: current ? 12 : 0 }}>
        <input
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={onKey}
          placeholder="问一件具体的事，例如：下周该不该换工作"
          disabled={guaStreaming}
          style={{ flex:1, padding:'6px 10px', fontSize:13, border:'1px solid #ccc' }}
        />
        <button className="btn-primary" onClick={() => castGua()} disabled={guaStreaming}>
          {guaStreaming ? '占算中…' : '起卦'}
        </button>
      </div>

      {current && (
        <div style={{ marginTop:8 }}>
          <div style={{ display:'flex', alignItems:'baseline', gap:14, marginBottom:6 }}>
            <span style={{ fontSize:48, lineHeight:1 }}>{current.symbol}</span>
            <div>
              <div className="serif" style={{ fontSize:18 }}>{current.name}</div>
              <div className="muted" style={{ fontSize:11 }}>上{current.upper} · 下{current.lower}</div>
              <div className="muted" style={{ fontSize:10, marginTop:2 }}>{current.drawnAt}</div>
            </div>
          </div>
          <div style={{ marginTop:8, fontSize:12, fontFamily:'"Songti SC", serif',
                        background:'#f7f3e9', padding:'8px 10px', borderLeft:'2px solid #b99' }}>
            <div><b>卦辞：</b>{current.guaci}</div>
            <div style={{ marginTop:4 }}><b>大象：</b>{current.daxiang}</div>
          </div>
          <div style={{ marginTop:10, fontSize:13, lineHeight:1.9, whiteSpace:'pre-wrap' }}>
            {showText ? <RichText text={showText} /> : (guaStreaming ? '生成中…' : '')}
          </div>
        </div>
      )}
      {error ? (
        <div style={{ marginTop:12 }}>
          <ErrorState
            title={uiError.title}
            detail={uiError.detail}
            retryable={uiError.retryable}
            onRetry={uiError.retryable ? () => castGua(question || current?.question) : undefined}
          />
        </div>
      ) : null}
    </div>
  );
}
